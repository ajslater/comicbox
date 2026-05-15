r"""
M7 tagging-quality measurement under -j N.

Runs the same fixture set at each jobs value with cold cache between
runs, parses per-fixture chosen IDs from the comicbox log, and uses
jobs=1's output as the ground-truth baseline. Quantifies how often
higher -j values reach a different decision than the serial path.

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
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path

_AUTO_WRITE_RE = re.compile(
    r"online (?P<source>\w+): auto-writing id=(?P<id>\d+) \(score=(?P<score>[\d.]+)\)"
)


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
    log_path: Path
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


def run_comicbox(
    fixtures: list[Fixture], jobs: int, log_path: Path
) -> tuple[int, float]:
    """Subprocess-invoke comicbox; return (exit_code, wall_seconds)."""
    cmd = [
        "uv",
        "run",
        "comicbox",
        "-n",
        "--online",
        "metron",
        "--policy",
        "normal",
        "--unattended",
        "--force-search",
        "-j",
        str(jobs),
        *[str(f.path) for f in fixtures],
    ]
    started = time.monotonic()
    with log_path.open("wb") as logf:
        result = subprocess.run(  # noqa: S603 — trusted argv
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.monotonic() - started
    return result.returncode, elapsed


def parse_chosen_ids(log_path: Path, fixtures: list[Fixture]) -> dict[str, int | None]:
    """
    Walk the log, slot each `auto-writing id=N` line under its fixture.

    Returns {fixture_path_str: chosen_metron_id_or_None}. Fixtures with
    no auto-write event get None (matcher SKIPPED or NO_MATCH or
    rate-limit dropped the candidate set).

    Parsing is path-driven not banner-driven: under -j N the log
    interleaves worker output. We scan for any line containing a
    fixture's path (which appears in the fixture-header banner) and
    associate subsequent same-thread log lines with it. Simpler
    fallback: pair auto-write lines with the nearest preceding path
    mention. Works because comicbox emits each fixture's path right
    before its processing starts on the same worker thread.
    """
    text = log_path.read_text(errors="replace")
    fixture_paths = {str(f.path): f for f in fixtures}
    chosen: dict[str, int | None] = {str(f.path): None for f in fixtures}

    # Sweep line by line; track which fixture each worker is currently
    # processing. Worker disambiguation via the timestamp+log lines is
    # noisy under -j, so we use a simpler heuristic: every time a path
    # appears in a log line, that's the "current" fixture for whatever
    # auto-write follows on subsequent lines until another path shows up.
    # Under -j this is imperfect (interleaving) but the auto-write line
    # for fixture X is *almost always* logged immediately after fixture
    # X's banner/path on the same worker.
    current_fixture: str | None = None
    for line in text.splitlines():
        for fp_str in fixture_paths:
            if fp_str in line:
                current_fixture = fp_str
                break
        match = _AUTO_WRITE_RE.search(line)
        if match and match.group("source") == "metron" and current_fixture is not None:
            chosen[current_fixture] = int(match.group("id"))
    return chosen


def score_outcome(
    fixtures: list[Fixture],
    jobs: int,
    wall_seconds: float,
    log_path: Path,
) -> JobsOutcome:
    """Bucket fixtures into decided / skipped given parsed chosen IDs."""
    chosen = parse_chosen_ids(log_path, fixtures)
    decided = sum(1 for f in fixtures if chosen.get(str(f.path)) is not None)
    skipped = len(fixtures) - decided
    return JobsOutcome(
        jobs=jobs,
        wall_seconds=wall_seconds,
        log_path=log_path,
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


def format_summary(fixtures: list[Fixture], outcomes: list[JobsOutcome]) -> str:
    """Build the comparison markdown. jobs=1 is the baseline."""
    lines = [
        "# M7 jobs-accuracy comparison",
        "",
        f"- Fixture count: {len(fixtures)}",
        "- Source: metron",
        "- Policy: normal, --unattended, --force-search",
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
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    jobs_values = [int(j) for j in args.jobs.split(",")]

    sys.stderr.write(
        f"running {len(fixtures)} fixtures x {len(jobs_values)} jobs values "
        f"({', '.join(str(j) for j in jobs_values)}) cold cache between\n"
    )

    outcomes: list[JobsOutcome] = []
    for jobs in jobs_values:
        wipe_metron_cache()
        before_rows = metron_cache_rows()
        log_path = args.output_dir / f"jobs-accuracy-{timestamp}-j{jobs}.log"
        sys.stderr.write(f"  jobs={jobs} → {log_path.name}\n")
        exit_code, wall = run_comicbox(fixtures, jobs, log_path)
        after_rows = metron_cache_rows()
        sys.stderr.write(
            f"  jobs={jobs} done: exit={exit_code} wall={wall / 60:.1f}m "
            f"metron requests={after_rows - before_rows}\n"
        )
        outcomes.append(score_outcome(fixtures, jobs, wall, log_path))

    summary = format_summary(fixtures, outcomes)
    summary_path = args.output_dir / "JOBS_ACCURACY_SUMMARY.md"
    summary_path.write_text(summary)
    sys.stdout.write(summary + "\n")
    sys.stdout.write(f"\nFull summary written to {summary_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
