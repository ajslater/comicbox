"""
M7 stress-test harness.

Subprocess-invokes the comicbox CLI in `-n --online --unattended -j N`
mode against a directory of fixtures, captures stdout/stderr to a log
file, and post-processes the run to compute:

  - total wall time
  - per-source upstream-request count (sqlite cache-row delta)
  - per-source request-rate (vs documented caps)
  - rate-limit retry events (parsed from log)
  - exception count (parsed from log)
  - prompt-lock contention (deferred — needs production observability)

Emits a markdown summary to stdout and to `<output-dir>/SUMMARY.md`.

Usage:

    uv run python -m tests.stress.run /path/to/fixtures
    uv run python -m tests.stress.run /path/to/fixtures --jobs 4 --limit 20
    uv run python -m tests.stress.run /path/to/fixtures --no-wipe-cache

Read-only against the fixtures: always passes `-n` (dry-run). Never
writes to archives.

Cache wipe is destructive (removes the sqlite caches under
`~/Library/Caches/comicbox/online/`). Defaults to enabled; pass
`--no-wipe-cache` to skip if you want a warm-cache run.
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

from platformdirs import user_cache_path

logger = logging.getLogger(__name__)

_EXTS: Final = (".cbz", ".cbr", ".cbt", ".cb7", ".pdf")
_SOURCES: Final = ("metron", "comicvine")
_RATE_LIMIT_LOG_RE: Final = re.compile(r"rate-limit, retrying in (?P<delay>[\d.]+)s")
_DOCUMENTED_CAPS: Final = {
    # Source name → (per-minute cap, per-hour cap, per-day cap).
    # Metron's per-day slot is the zero-donor base tier (up to 25,000 for
    # OpenCollective donors); only the per-minute and per-hour slots are
    # checked by _rate_row, the per-day slot is informational.
    "metron": (20, None, 5000),
    "comicvine": (60, 200, None),
}


@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    """Row counts and file sizes for each source's response cache."""

    rows: dict[str, int]
    bytes: dict[str, int]


def _cache_dir() -> Path:
    return user_cache_path("comicbox") / "online"


def _cache_path(source: str) -> Path:
    return _cache_dir() / f"{source}_cache.sqlite"


def _row_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            return sum(
                conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                for t in tables
            )
    except sqlite3.Error as exc:
        logger.warning("cache row-count failed for %s: %s", db_path, exc)
        return 0


def snapshot_caches() -> CacheSnapshot:
    rows: dict[str, int] = {}
    sizes: dict[str, int] = {}
    for source in _SOURCES:
        path = _cache_path(source)
        rows[source] = _row_count(path)
        sizes[source] = path.stat().st_size if path.exists() else 0
    return CacheSnapshot(rows=rows, bytes=sizes)


def wipe_caches() -> list[Path]:
    """Remove every per-source response cache. Returns the paths removed."""
    removed: list[Path] = []
    for source in _SOURCES:
        path = _cache_path(source)
        if path.exists():
            path.unlink()
            removed.append(path)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
                removed.append(sidecar)
    return removed


def discover_fixtures(root: Path, limit: int | None) -> list[Path]:
    """Recursively find comic-archive files under `root`."""
    if root.is_file():
        return [root]
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in _EXTS)
    if limit is not None:
        files = files[:limit]
    return files


def run_comicbox(
    fixtures: list[Path],
    jobs: int,
    log_path: Path,
    sources: str,
) -> tuple[int, float]:
    """Subprocess-invoke comicbox; return (exit_code, wall_seconds)."""
    cmd = [
        "uv",
        "run",
        "comicbox",
        "-n",
        "--online",
        sources,
        "--unattended",
        "-j",
        str(jobs),
        *[str(p) for p in fixtures],
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


def parse_log(log_path: Path) -> dict[str, int]:
    """
    Count interesting log events. Returns a dict of metric → count.

    WARNING count excludes "No action performed" — that's the expected
    dry-run message from comicbox when invoked without `--write`, one
    per file, and it would otherwise drown the genuine WARNINGs.
    """
    metrics = {
        "rate_limit_retries": 0,
        "warnings": 0,
        "errors": 0,
        "exceptions": 0,
    }
    if not log_path.exists():
        return metrics
    text = log_path.read_text(errors="replace")
    metrics["rate_limit_retries"] = len(_RATE_LIMIT_LOG_RE.findall(text))
    warning_lines = re.findall(r"WARNING.*", text)
    metrics["warnings"] = sum(
        1 for line in warning_lines if "No action performed" not in line
    )
    metrics["errors"] = len(re.findall(r"\bERROR\b", text))
    metrics["exceptions"] = len(
        re.findall(r"^Traceback \(most recent call last\):", text, re.MULTILINE)
    )
    return metrics


def format_rate_check(source: str, requests: int, wall_seconds: float) -> str:
    """
    Compare observed rate to documented caps. Returns a markdown row.

    Per-minute caps are checked against the observed rate directly.
    Per-hour caps are only checked when the run is ≥1 hour — short
    bursts can briefly exceed the per-hour rate projection without
    ever hitting the hourly wall (the in-process limiter would clip).
    """
    per_min_cap, per_hour_cap, _ = _DOCUMENTED_CAPS.get(source, (None, None, None))
    observed_per_min = (requests / wall_seconds * 60) if wall_seconds > 0 else 0.0
    cap_str = f"{per_min_cap}/min" if per_min_cap else "—"
    status = "OK"
    if per_min_cap and observed_per_min > per_min_cap * 1.05:
        status = f"OVER ({observed_per_min:.1f}/min vs {per_min_cap})"
    elif per_hour_cap and wall_seconds >= 3600 and requests > per_hour_cap * 1.05:
        status = f"OVER hourly ({requests}/hr vs {per_hour_cap})"
    return (
        f"| {source} | {requests} | {observed_per_min:.2f}/min | {cap_str} | {status} |"
    )


@dataclass(frozen=True, slots=True)
class RunResult:
    """Container for everything the summary needs from a stress run."""

    args: argparse.Namespace
    fixture_count: int
    fixtures_root: Path
    wall_seconds: float
    before: CacheSnapshot
    after: CacheSnapshot
    metrics: dict[str, int]
    exit_code: int
    log_path: Path


def _per_source_rate_failures(r: RunResult) -> Iterator[str]:
    """Yield human-readable rate-limit violations per source."""
    if r.wall_seconds <= 0:
        return
    for source in _SOURCES:
        per_min_cap, per_hour_cap, _ = _DOCUMENTED_CAPS.get(source, (None, None, None))
        delta = r.after.rows.get(source, 0) - r.before.rows.get(source, 0)
        observed_per_min = delta / r.wall_seconds * 60
        if per_min_cap and observed_per_min > per_min_cap * 1.05:
            yield (
                f"{source} exceeded documented cap "
                f"({observed_per_min:.1f}/min vs {per_min_cap}/min)."
            )
        if per_hour_cap and r.wall_seconds >= 3600 and delta > per_hour_cap * 1.05:
            yield (
                f"{source} exceeded hourly cap "
                f"({delta} requests in {r.wall_seconds / 3600:.1f}h vs "
                f"{per_hour_cap}/hr)."
            )


def _collect_failures(r: RunResult) -> list[str]:
    """Gather the full pass/fail diagnostics list for the summary."""
    failures: list[str] = []
    if r.exit_code != 0:
        failures.append(f"comicbox exited with non-zero status ({r.exit_code}).")
    if r.metrics["exceptions"] > 0:
        failures.append(f"{r.metrics['exceptions']} traceback(s) in the log.")
    failures.extend(_per_source_rate_failures(r))
    return failures


def build_summary(r: RunResult) -> str:
    """Format the markdown summary."""
    lines = [
        "# M7 stress-test summary",
        "",
        f"- Fixtures root: `{r.fixtures_root}`",
        f"- Fixture count: {r.fixture_count}",
        f"- Jobs: {r.args.jobs}",
        f"- Sources: {r.args.sources}",
        f"- Cache wiped before run: {not r.args.no_wipe_cache}",
        f"- Wall time: {r.wall_seconds:.1f}s ({r.wall_seconds / 60:.1f}m)",
        f"- Exit code: {r.exit_code}",
        f"- Log file: `{r.log_path}`",
        "",
        "## Per-source upstream requests (sqlite cache-row delta)",
        "",
        "| Source | New rows | Observed rate | Documented cap | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for source in _SOURCES:
        delta = r.after.rows.get(source, 0) - r.before.rows.get(source, 0)
        lines.append(format_rate_check(source, delta, r.wall_seconds))
    lines += [
        "",
        "## Log-derived metrics",
        "",
        f"- Rate-limit retries: **{r.metrics['rate_limit_retries']}**",
        f"- WARNING lines: {r.metrics['warnings']}",
        f"- ERROR lines: {r.metrics['errors']}",
        f"- Tracebacks: **{r.metrics['exceptions']}**",
        "",
        "## Pass/fail",
        "",
    ]
    failures = _collect_failures(r)
    if not failures:
        lines.append("**PASS** — no rate-limit violations, no exceptions.")
    else:
        lines.append("**FAIL** — issues observed:")
        lines.extend(f"- {f}" for f in failures)
    lines += [
        "",
        "## Not measured (follow-up needed)",
        "",
        "- **Prompt-lock contention.** `--unattended` makes the matcher SKIP",
        "  instead of prompting, so `_PROMPT_LOCK` is never acquired. To",
        "  validate prompt UX under load needs a programmatic selector and",
        "  production observability (timing logs around the lock). Tracked",
        "  separately.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M7 stress-test harness — see tests/stress/README.md",
    )
    parser.add_argument(
        "fixtures",
        type=Path,
        help="Directory of fixtures (recurses) or single comic file",
    )
    parser.add_argument(
        "--jobs", "-j", type=int, default=8, help="Workers (default: 8)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap fixture count (smoke runs)",
    )
    parser.add_argument(
        "--sources",
        default="metron,comicvine",
        help="Comma-separated --online value (default: metron,comicvine)",
    )
    parser.add_argument(
        "--no-wipe-cache",
        action="store_true",
        help="Skip the pre-run cache wipe (warm-cache run)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/stress/output"),
        help="Where to write the log + summary (default: tests/stress/output)",
    )
    args = parser.parse_args(argv)

    if not args.fixtures.exists():
        sys.stderr.write(f"fixtures path does not exist: {args.fixtures}\n")
        return 2

    fixtures = discover_fixtures(args.fixtures, args.limit)
    if not fixtures:
        sys.stderr.write(f"no fixtures found under {args.fixtures}\n")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    log_path = args.output_dir / f"run-{timestamp}.log"
    summary_path = args.output_dir / "SUMMARY.md"

    if not args.no_wipe_cache:
        removed = wipe_caches()
        sys.stderr.write(f"wiped {len(removed)} cache file(s)\n")
        for p in removed:
            sys.stderr.write(f"  - {p}\n")

    before = snapshot_caches()
    sys.stderr.write(
        f"running comicbox -j {args.jobs} against {len(fixtures)} fixtures "
        f"({args.sources}) — log: {log_path}\n"
    )
    exit_code, wall = run_comicbox(fixtures, args.jobs, log_path, args.sources)
    after = snapshot_caches()

    metrics = parse_log(log_path)
    summary = build_summary(
        RunResult(
            args=args,
            fixture_count=len(fixtures),
            fixtures_root=args.fixtures,
            wall_seconds=wall,
            before=before,
            after=after,
            metrics=metrics,
            exit_code=exit_code,
            log_path=log_path,
        )
    )
    summary_path.write_text(summary)
    sys.stdout.write(summary + "\n")
    sys.stdout.write(f"\nFull summary written to {summary_path}\n")
    return 0 if exit_code == 0 and metrics["exceptions"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
