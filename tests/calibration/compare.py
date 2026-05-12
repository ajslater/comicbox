r"""
Diff two calibration outcomes files.

Used during Phase B's experiment matrix to compare runs at different
api_budget settings. Highlights:

- Per-fixture flips (correct → wrong, wrong → correct, etc.)
- Aggregate accuracy delta
- Per-source API-call totals (the cost side of the trade)

Usage:

    uv run python -m tests.calibration.compare \
        tests/calibration/fixtures.outcomes.balanced.json \
        tests/calibration/fixtures.outcomes.fast-pf07-mv5.json

The first file is the "baseline" and the second is the "candidate." The
output reads as "what changed when switching from baseline to
candidate" — fixtures that flipped wrong→correct are wins; correct→wrong
are regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


def _load(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Index outcome entries by (file, source) for O(1) lookup."""
    raw = json.loads(path.read_text())
    return {(str(e["file"]), str(e["source"])): e for e in raw}


def _outcome_tag(entry: dict[str, Any]) -> str:
    """Stringly-typed outcome label (mirrors run.py's `_classify_outcome`)."""
    return str(entry.get("outcome", "?"))


def _flip_category(before_tag: str, after_tag: str) -> str | None:
    """
    Categorize a (before, after) outcome pair.

    Returns one of:
    - "WIN"      — wrong/error/no_candidates  →  correct
    - "REGRESS"  — correct  →  wrong/error/no_candidates
    - "NEUTRAL"  — wrong→error or similar wiggle within the failure family
    - None       — no change worth reporting (correct→correct, etc.)
    """
    if before_tag == after_tag:
        return None
    if after_tag == "correct" and before_tag != "correct":
        return "WIN"
    if before_tag == "correct" and after_tag != "correct":
        return "REGRESS"
    return "NEUTRAL"


def _sum_call_counts(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Sum the per-method api_call_counts across all entries."""
    totals: dict[str, int] = {}
    for e in entries:
        for method, n in (e.get("api_call_counts") or {}).items():
            totals[method] = totals.get(method, 0) + int(n)
    return totals


def _aggregate(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Bucket count per outcome label."""
    buckets: dict[str, int] = {}
    for e in entries:
        tag = _outcome_tag(e)
        buckets[tag] = buckets.get(tag, 0) + 1
    return buckets


def _print_aggregate(label: str, agg: dict[str, int], totals: dict[str, int]) -> None:
    """Print one side's summary (correct/wrong/no_candidates/etc. + cost)."""
    print(f"\n=== {label} ===")  # noqa: T201
    for tag in ("correct", "wrong", "no_candidates", "error", "no_expected_id"):
        if tag in agg:
            print(f"  {tag:18}: {agg[tag]}")  # noqa: T201
    if totals:
        total_calls = sum(totals.values())
        print(f"  api calls (total)  : {total_calls}")  # noqa: T201
        for method in sorted(totals):
            print(f"    {method:30}: {totals[method]}")  # noqa: T201


def _print_flips(
    flips: list[tuple[str, tuple[str, str], dict[str, Any], dict[str, Any]]],
) -> None:
    """List the (file, source) pairs that changed between runs."""
    if not flips:
        print("\nNo per-fixture flips between the two runs.")  # noqa: T201
        return
    flips.sort(key=lambda x: (x[0], x[1][1], x[1][0]))
    print("\n--- Per-fixture flips ---")  # noqa: T201
    for category, (file_path, source), before, after in flips:
        before_id = before.get("top_issue_id")
        after_id = after.get("top_issue_id")
        before_score = before.get("top_score") or 0.0
        after_score = after.get("top_score") or 0.0
        print(  # noqa: T201
            f"  [{category}] {source}: {Path(file_path).name}\n"
            f"      before: {_outcome_tag(before)} got={before_id} "
            f"score={before_score:.2f}\n"
            f"      after:  {_outcome_tag(after)} got={after_id} "
            f"score={after_score:.2f}"
        )


def _compute_flips(
    before: dict[tuple[str, str], dict[str, Any]],
    after: dict[tuple[str, str], dict[str, Any]],
) -> list[tuple[str, tuple[str, str], dict[str, Any], dict[str, Any]]]:
    """Walk both outcome sets, emit per-(file, source) flips with category."""
    flips: list[tuple[str, tuple[str, str], dict[str, Any], dict[str, Any]]] = []
    common = set(before) & set(after)
    for key in common:
        b = before[key]
        a = after[key]
        category = _flip_category(_outcome_tag(b), _outcome_tag(a))
        if category is None:
            continue
        flips.append((category, key, b, a))
    return flips


def _print_unique_keys(
    before: dict[tuple[str, str], dict[str, Any]],
    after: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Note fixtures present in one file but not the other."""
    only_before = set(before) - set(after)
    only_after = set(after) - set(before)
    if only_before:
        print(  # noqa: T201
            f"\n  {len(only_before)} fixture(s) only in baseline "
            f"(present in before, missing in after) — partial-run artifact"
        )
    if only_after:
        print(  # noqa: T201
            f"  {len(only_after)} fixture(s) only in candidate "
            f"(present in after, missing in before)"
        )


def main() -> int:
    """Diff two outcomes files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="Baseline outcomes file")
    parser.add_argument("after", type=Path, help="Candidate outcomes file")
    args = parser.parse_args()

    if not args.before.exists():
        sys.stderr.write(f"baseline not found: {args.before}\n")
        return 1
    if not args.after.exists():
        sys.stderr.write(f"candidate not found: {args.after}\n")
        return 1

    before = _load(args.before)
    after = _load(args.after)

    print(f"Baseline:  {args.before}  ({len(before)} entries)")  # noqa: T201
    print(f"Candidate: {args.after}  ({len(after)} entries)")  # noqa: T201

    _print_aggregate(
        "baseline", _aggregate(before.values()), _sum_call_counts(before.values())
    )
    _print_aggregate(
        "candidate", _aggregate(after.values()), _sum_call_counts(after.values())
    )

    flips = _compute_flips(before, after)
    wins = sum(1 for f in flips if f[0] == "WIN")
    regressions = sum(1 for f in flips if f[0] == "REGRESS")
    neutral = sum(1 for f in flips if f[0] == "NEUTRAL")
    print(  # noqa: T201
        f"\nFlips: {wins} win, {regressions} regress, {neutral} neutral"
    )

    _print_flips(flips)
    _print_unique_keys(before, after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
