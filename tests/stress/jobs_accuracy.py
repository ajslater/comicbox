r"""
M7 tagging-quality measurement under -j N.

Runs the same fixture set at each jobs value with cold cache between
runs and uses jobs=1's output as the ground-truth baseline.
Quantifies how often higher -j values reach a different decision
than the serial path.

The bootstrap'd labeled fixtures don't include Metron IDs (only CV),
and CV's hourly cap makes a labeled CV sweep expensive (~1.5 hr
wall regardless of jobs). The cleaner direct measurement is "does
parallelism change the matcher's choice vs the serial path?" — that
question doesn't need labels, just a reliable jobs=1 reference.

Targets Metron — that's the contention-prone source per
2026-05-15-stress-100 (high-fan-out fixtures fan out to 20+
candidate series under -j 8, exhausting retries).

Uses `--force-search` so fixtures with stored Metron IDs still
exercise the matcher path (without this, the explicit-id shortcut
bypasses search entirely → -j has no effect).

Architecture: drives `comicbox.cli.main(argv)` in-process so we can
monkeypatch `ComicboxOnlineLookup._accept_candidate` with a
recording hook. Per-fixture chosen IDs are captured directly
without log parsing, which means the harness is robust under heavy
-j N log interleaving (a previous subprocess-based iteration broke
under -j 8 — caught 2 of 39 actual auto-writes).

Usage:

    uv run python -m tests.stress.jobs_accuracy \\
        tests/calibration/fixtures-jobs.json \\
        --jobs 1,4,8 --limit 50

Read-only against the fixtures: passes `-n` (dry-run). No archive
mutations. Destructive to the Metron sqlite cache between runs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path

from comicbox import cli as _cli_module
from comicbox.box import online_lookup as _lookup_module


@dataclass(frozen=True, slots=True)
class Fixture:
    """One labeled fixture: file path + expected source ids."""

    path: Path
    metron: int | None
    comicvine: int | None


@dataclass(frozen=True, slots=True)
class JobsOutcome:
    """One -j value's result: per-fixture chosen IDs."""

    jobs: int
    wall_seconds: float
    chosen_by_fixture: dict[str, int | None]  # path string → chosen metron id
    # Count of fixtures with an auto-write decision; the rest were skipped.
    decided: int
    skipped: int


def load_fixtures(path: Path, limit: int | None) -> list[Fixture]:
    """Read fixtures.json and return a list of fixtures with existing files."""
    data = json.loads(path.read_text())
    fixtures = [
        Fixture(
            path=Path(entry["file"]).expanduser(),
            metron=entry.get("metron"),
            comicvine=entry.get("comicvine"),
        )
        for entry in data
    ]
    fixtures = [f for f in fixtures if f.path.exists()]
    if limit is not None:
        fixtures = fixtures[:limit]
    return fixtures


def wipe_metron_cache() -> Path | None:
    """Remove Metron's response cache. Returns the path if removed."""
    cache_dir = user_cache_path("comicbox") / "online"
    path = cache_dir / "metron_cache.sqlite"
    if not path.exists():
        return None
    path.unlink()
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    return path


def metron_cache_rows() -> int:
    """Row count in the metron response cache (request count proxy)."""
    cache_dir = user_cache_path("comicbox") / "online"
    path = cache_dir / "metron_cache.sqlite"
    if not path.exists():
        return 0
    try:
        with sqlite3.connect(path) as conn:
            return conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
    except sqlite3.Error:
        return 0


def build_cli_argv(
    fixtures: list[Fixture], jobs: int, threshold: float | None = None
) -> list[str]:
    """Build the argv that `comicbox.cli.main` would parse."""
    argv = [
        "-n",
        "--online",
        "metron",
        "--policy",
        "normal",
        "--unattended",
        "--force-search",
        "-j",
        str(jobs),
    ]
    if threshold is not None:
        argv += ["--confidence-threshold", f"metron:{threshold}"]
    argv += [str(f.path) for f in fixtures]
    return argv


def run_with_recording_hook(
    fixtures: list[Fixture],
    jobs: int,
    threshold: float | None,
) -> tuple[dict[str, int | None], float]:
    """
    Drive `comicbox.cli.main(argv)` with a monkeypatched recording hook.

    Captures the (fixture_path → metron_id) decision dict by patching
    `ComicboxOnlineLookup._accept_candidate` to record before calling
    the original. Robust under heavy -j N log interleaving because
    we're hooked into the in-process matcher state, not parsing
    interleaved log lines.

    Returns (chosen_by_fixture, wall_seconds).
    """
    chosen: dict[str, int | None] = {str(f.path): None for f in fixtures}
    chosen_lock = threading.Lock()
    original = _lookup_module.ComicboxOnlineLookup._accept_candidate

    def recording_accept(self, source, candidate) -> bool:
        if source.name == "metron":
            path = getattr(self, "_path", None)
            if path is not None:
                with chosen_lock:
                    chosen[str(path)] = candidate.issue_id
        return original(self, source, candidate)

    _lookup_module.ComicboxOnlineLookup._accept_candidate = recording_accept
    started = time.monotonic()
    try:
        _cli_module.main(build_cli_argv(fixtures, jobs, threshold))
    finally:
        _lookup_module.ComicboxOnlineLookup._accept_candidate = original
    return chosen, time.monotonic() - started


def score_outcome(
    fixtures: list[Fixture],
    jobs: int,
    wall_seconds: float,
    chosen: dict[str, int | None],
) -> JobsOutcome:
    """Bucket fixtures into decided / skipped given recorded chosen IDs."""
    decided = sum(1 for f in fixtures if chosen.get(str(f.path)) is not None)
    skipped = len(fixtures) - decided
    return JobsOutcome(
        jobs=jobs,
        wall_seconds=wall_seconds,
        chosen_by_fixture=chosen,
        decided=decided,
        skipped=skipped,
    )


@dataclass(frozen=True, slots=True)
class _Diff:
    """Categorised differences between two outcomes."""

    same: int
    changed: list[tuple[str, int | None, int | None]]
    lost: list[tuple[str, int | None]]
    gained: list[tuple[str, int | None]]
    total: int


def _diff_outcomes(baseline: JobsOutcome, other: JobsOutcome) -> _Diff:
    """Bucket per-fixture pairs into same / changed-id / lost / gained."""
    same = 0
    changed: list[tuple[str, int | None, int | None]] = []
    lost: list[tuple[str, int | None]] = []
    gained: list[tuple[str, int | None]] = []
    for fp_str, base_id in baseline.chosen_by_fixture.items():
        other_id = other.chosen_by_fixture.get(fp_str)
        if base_id == other_id:
            same += 1
        elif base_id is None:
            gained.append((fp_str, other_id))
        elif other_id is None:
            lost.append((fp_str, base_id))
        else:
            changed.append((fp_str, base_id, other_id))
    return _Diff(
        same=same,
        changed=changed,
        lost=lost,
        gained=gained,
        total=len(baseline.chosen_by_fixture),
    )


def _format_diff_section(jobs: int, baseline_jobs: int, diff: _Diff) -> list[str]:
    """Render one baseline-vs-other comparison as markdown lines."""
    pct = f"{diff.same / diff.total * 100:.1f}%" if diff.total else "—"
    lines = [
        f"### jobs={jobs} vs jobs={baseline_jobs}",
        "",
        f"- Same outcome: **{diff.same}/{diff.total}** ({pct})",
        f"- Changed identity (different ID): **{len(diff.changed)}**",
        f"- Lost (baseline decided, parallel SKIPPED): **{len(diff.lost)}**",
        f"- Gained (baseline SKIPPED, parallel decided): **{len(diff.gained)}**",
        "",
    ]
    if diff.changed:
        lines += [
            "**Identity changes:**",
            "",
            "| Fixture | jobs=1 | jobs=N |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| {Path(fp).name} | {base_id} | {other_id} |"
            for fp, base_id, other_id in diff.changed[:15]
        )
        if len(diff.changed) > 15:
            lines.append(f"\n_... and {len(diff.changed) - 15} more_")
        lines.append("")
    if diff.lost:
        lines += [
            "**Decision losses (parallel skipped what serial decided):**",
            "",
        ]
        lines.extend(
            f"- `{Path(fp).name}` (serial picked {base_id})"
            for fp, base_id in diff.lost[:10]
        )
        if len(diff.lost) > 10:
            lines.append(f"\n_... and {len(diff.lost) - 10} more_")
        lines.append("")
    return lines


def format_summary(
    fixtures: list[Fixture],
    outcomes: list[JobsOutcome],
    threshold: float | None = None,
) -> str:
    """Build the comparison markdown. jobs=1 is the baseline."""
    threshold_line = (
        f"- Confidence threshold: {threshold} (overridden via --threshold)"
        if threshold is not None
        else "- Confidence threshold: 0.95 (production default)"
    )
    lines = [
        "# M7 jobs-accuracy comparison",
        "",
        f"- Fixture count: {len(fixtures)}",
        "- Source: metron",
        "- Policy: normal, --unattended, --force-search",
        threshold_line,
        "- Cache: wiped before each run (cold)",
        "- Baseline: jobs=1 (serial, no contention)",
        "",
        "## Per-jobs outcome",
        "",
        "| Jobs | Wall (min) | Decided | Skipped |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {o.jobs} | {o.wall_seconds / 60:.1f} | {o.decided} | {o.skipped} |"
        for o in outcomes
    )
    lines += ["", "## Diff vs jobs=1 baseline", ""]
    if not outcomes:
        return "\n".join(lines)
    baseline = outcomes[0]
    for o in outcomes[1:]:
        lines.extend(
            _format_diff_section(o.jobs, baseline.jobs, _diff_outcomes(baseline, o))
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M7 jobs-accuracy comparison — see tests/stress/README.md"
    )
    parser.add_argument(
        "fixtures_json",
        type=Path,
        help="Path to labeled fixtures.json (bootstrap via tests.calibration.bootstrap)",
    )
    parser.add_argument(
        "--jobs",
        default="1,4,8",
        help="Comma-separated list of -j values to test (default: 1,4,8)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cap fixture count per run (default: 50)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "Override `--confidence-threshold metron:<v>` so the matcher "
            "auto-writes any candidate above <v> instead of the production "
            "0.95 default. Use 0.50 to force decisions on every above-"
            "min_confidence candidate (handy when the labeled fixture set "
            "is too thin for auto-writes to land naturally)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/stress/output"),
        help="Where to write logs + summary",
    )
    args = parser.parse_args(argv)

    if not args.fixtures_json.exists():
        sys.stderr.write(f"fixtures.json not found: {args.fixtures_json}\n")
        return 2

    fixtures = load_fixtures(args.fixtures_json, args.limit)
    if not fixtures:
        sys.stderr.write("no usable fixtures (need labels + existing files)\n")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    jobs_values = [int(j) for j in args.jobs.split(",")]

    sys.stderr.write(
        f"running {len(fixtures)} fixtures x {len(jobs_values)} jobs values "
        f"({', '.join(str(j) for j in jobs_values)}) cold cache between\n"
    )

    outcomes: list[JobsOutcome] = []
    for jobs in jobs_values:
        wipe_metron_cache()
        before_rows = metron_cache_rows()
        sys.stderr.write(f"  jobs={jobs} ...\n")
        chosen, wall = run_with_recording_hook(fixtures, jobs, args.threshold)
        after_rows = metron_cache_rows()
        decided_now = sum(1 for v in chosen.values() if v is not None)
        sys.stderr.write(
            f"  jobs={jobs} done: wall={wall / 60:.1f}m "
            f"metron requests={after_rows - before_rows} "
            f"decided={decided_now}/{len(fixtures)}\n"
        )
        outcomes.append(score_outcome(fixtures, jobs, wall, chosen))

    summary = format_summary(fixtures, outcomes, args.threshold)
    summary_path = args.output_dir / "JOBS_ACCURACY_SUMMARY.md"
    summary_path.write_text(summary)
    sys.stdout.write(summary + "\n")
    sys.stdout.write(f"\nFull summary written to {summary_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
