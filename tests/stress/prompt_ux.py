r"""
M7 prompt-UX validation under `-j N`.

Complements `tests/stress/run.py` (rate-limiter compliance under
`--unattended`) by closing the second half of M7 acceptance: prompt
serialization, no deadlocks, readable output under parallel prompts.

Monkeypatches `comicbox.box.online_lookup.cli_selector` with a
recording selector that:

  - logs (enter_ns, exit_ns, thread_id, file_path) per selector call
  - sleeps `--think-time` seconds (simulates user reading the prompt)
  - returns `("skip", None)` so the matcher declines the candidate
    and the file is left untagged (we're not testing tagging quality,
    just the lock).

Drives `Runner.run()` programmatically with the real parallel path
(`comicbox.run.Runner._run_parallel`) so the production code path —
ThreadPoolExecutor, `_PROMPT_LOCK` acquire/release — runs end-to-end.

After the run, verifies:

  - **Serialization**: no two recorded events overlap. The
    `_PROMPT_LOCK` guarantees this; this check would fail if the
    lock were missing or scoped wrong.
  - **No deadlocks**: every fixture that triggered a prompt also
    completed it (no orphaned enter without exit). Implicit in
    `Runner.run()` returning at all.
  - **Wall-time sanity**: total wall time >= N_prompts * think_time
    (proves serialization wasn't bypassed somehow).

Usage:

    uv run python -m tests.stress.prompt_ux ~/Milliways/Comics/Test \\
        --limit 20 --jobs 8 --think-time 0.5

Read-only against the fixtures: passes `-n` and `policy=always-prompt`
with our recording selector returning `skip`, so no archive writes.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comicbox import cli as _cli_module
from comicbox.box import online_lookup as _lookup_module

_EXTS = (".cbz", ".cbr", ".cbt", ".cb7", ".pdf")


@dataclass(frozen=True, slots=True)
class PromptEvent:
    """One selector call: when it entered, when it exited, where, who."""

    file_path: str
    thread_id: int
    enter_ns: int
    exit_ns: int


@dataclass(frozen=True, slots=True)
class PromptUXResult:
    """Outcome of the run + the derived pass/fail signals."""

    events: list[PromptEvent]
    wall_seconds: float
    overlaps: list[tuple[PromptEvent, PromptEvent]]
    distinct_threads: int


def make_recording_selector(
    think_time_s: float,
    events: list[PromptEvent],
    events_lock: threading.Lock,
):
    """Build a selector callback that records timing then returns 'skip'."""

    def selector(_profile, _candidates, ctx) -> tuple[str, Any]:
        enter_ns = time.monotonic_ns()
        time.sleep(think_time_s)
        exit_ns = time.monotonic_ns()
        event = PromptEvent(
            file_path=str(ctx.file_path) if ctx.file_path else "<unknown>",
            thread_id=threading.get_ident(),
            enter_ns=enter_ns,
            exit_ns=exit_ns,
        )
        with events_lock:
            events.append(event)
        return ("skip", None)

    return selector


def discover_fixtures(root: Path, limit: int | None) -> list[Path]:
    """Recursively find comic-archive files under `root`."""
    if root.is_file():
        return [root]
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in _EXTS)
    if limit is not None:
        files = files[:limit]
    return files


def detect_overlaps(events: list[PromptEvent]) -> list[tuple[PromptEvent, PromptEvent]]:
    """
    Return pairs of events whose [enter_ns, exit_ns] intervals overlap.

    Under a working `_PROMPT_LOCK` this list is always empty.
    """
    overlaps: list[tuple[PromptEvent, PromptEvent]] = []
    sorted_events = sorted(events, key=lambda e: e.enter_ns)
    for i, ev_a in enumerate(sorted_events):
        for ev_b in sorted_events[i + 1 :]:
            if ev_b.enter_ns >= ev_a.exit_ns:
                break
            overlaps.append((ev_a, ev_b))
    return overlaps


def build_cli_argv(args: argparse.Namespace, fixtures: list[Path]) -> list[str]:
    """
    Build the argv that `comicbox.cli.main` would parse.

    `--policy always-prompt` forces every candidate into the PROMPT
    resolution path, maximising lock contention regardless of how
    ambiguous the fixtures actually are.
    """
    return [
        "-n",
        "--online",
        "metron,comicvine",
        "--policy",
        "always-prompt",
        "--force-search",
        "--api-budget",
        "fast",
        "-j",
        str(args.jobs),
        *[str(p) for p in fixtures],
    ]


def run_with_recording_selector(
    args: argparse.Namespace, fixtures: list[Path]
) -> PromptUXResult:
    """Monkeypatch the selector, run, restore. Return the timing data."""
    events: list[PromptEvent] = []
    events_lock = threading.Lock()
    recording_selector = make_recording_selector(args.think_time, events, events_lock)
    original_selector = _lookup_module.cli_selector
    _lookup_module.cli_selector = recording_selector  # type: ignore[assignment]
    started = time.monotonic()
    try:
        argv = build_cli_argv(args, fixtures)
        _cli_module.main(argv)
    finally:
        _lookup_module.cli_selector = original_selector  # type: ignore[assignment]
    wall_seconds = time.monotonic() - started
    return PromptUXResult(
        events=events,
        wall_seconds=wall_seconds,
        overlaps=detect_overlaps(events),
        distinct_threads=len({e.thread_id for e in events}),
    )


def format_summary(args: argparse.Namespace, result: PromptUXResult) -> str:
    """Build the markdown summary."""
    lines = [
        "# M7 prompt-UX summary",
        "",
        f"- Jobs: {args.jobs}",
        f"- Think-time per prompt: {args.think_time}s",
        f"- Wall time: {result.wall_seconds:.2f}s",
        f"- Prompts recorded: {len(result.events)}",
        f"- Distinct worker threads: {result.distinct_threads}",
        f"- Overlapping prompts: **{len(result.overlaps)}**",
        "",
    ]
    if result.events:
        min_expected = len(result.events) * args.think_time
        lines.append(
            f"- Min expected wall time (N x think): {min_expected:.2f}s "
            f"({'OK' if result.wall_seconds >= min_expected * 0.95 else 'WALL TOO LOW'})"
        )
    lines.append("")
    if result.overlaps:
        lines.append("## Overlap detail (lock failure)")
        lines.append("")
        for ev_a, ev_b in result.overlaps[:10]:
            lines.append(
                f"- thread {ev_a.thread_id} `{ev_a.file_path}` "
                f"[{ev_a.enter_ns} .. {ev_a.exit_ns}] overlaps with "
                f"thread {ev_b.thread_id} `{ev_b.file_path}` "
                f"[{ev_b.enter_ns} .. {ev_b.exit_ns}]"
            )
        if len(result.overlaps) > 10:
            lines.append(f"- ... and {len(result.overlaps) - 10} more")
        lines.append("")
    lines += [
        "## Pass/fail",
        "",
    ]
    failures: list[str] = []
    if not result.events:
        failures.append(
            "No prompts recorded — the test didn't actually exercise the "
            "selector path. Check that the fixtures trigger online lookup."
        )
    if result.overlaps:
        failures.append(
            f"{len(result.overlaps)} overlapping prompt(s) detected — "
            "`_PROMPT_LOCK` is not serialising correctly."
        )
    if result.events:
        min_expected = len(result.events) * args.think_time
        if result.wall_seconds < min_expected * 0.95:
            failures.append(
                f"Wall time {result.wall_seconds:.2f}s is shorter than the "
                f"minimum serialised expectation {min_expected:.2f}s — "
                "selectors may not be serialising."
            )
    if not failures:
        lines.append(
            "**PASS** — all prompts serialised, no deadlocks, wall time "
            "matches serialised execution."
        )
    else:
        lines.append("**FAIL** — issues observed:")
        lines.extend(f"- {f}" for f in failures)
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M7 prompt-UX validation — see tests/stress/README.md"
    )
    parser.add_argument(
        "fixtures",
        type=Path,
        help="Directory of fixtures (recurses) or single comic file",
    )
    parser.add_argument(
        "--jobs", "-j", type=int, default=8, help="Workers (default: 8)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap fixture count")
    parser.add_argument(
        "--think-time",
        type=float,
        default=0.5,
        help="Seconds the recording selector sleeps per prompt (default: 0.5)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/stress/output"),
        help="Where to write the summary",
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
    sys.stderr.write(
        f"running -j {args.jobs} against {len(fixtures)} fixtures "
        f"(always-prompt, think_time={args.think_time}s)\n"
    )

    result = run_with_recording_selector(args, fixtures)

    summary = format_summary(args, result)
    summary_path = args.output_dir / "PROMPT_UX_SUMMARY.md"
    summary_path.write_text(summary)
    sys.stdout.write(summary + "\n")
    sys.stdout.write(f"Full summary written to {summary_path}\n")

    return 0 if not result.overlaps and result.events else 1


if __name__ == "__main__":
    sys.exit(main())
