r"""
Print the cumulative calibration report from a saved outcomes.json.

`run.py` prints a per-chunk report at the end of each chunk. After a
chunked run completes, the canonical outcomes file holds the union of
every chunk — but there's no built-in way to see the cross-chunk
totals. This script reads an outcomes.json and renders the same
`_format_report` view `run.py` produces, but over the whole file.

Usage:

    # Canonical outcomes (the default fixtures-{stem}.outcomes.json):
    uv run python -m tests.calibration.summarize \\
        --fixtures tests/calibration/fixtures-slimlib.json

    # A labeled outcomes file (e.g. Phase B matrix runs):
    uv run python -m tests.calibration.summarize \\
        --outcomes tests/calibration/fixtures.outcomes.fast.json

The output mirrors `run.py`'s end-of-chunk report: per-source correct /
wrong / no_candidates / errored counts, accuracy on labeled fixtures,
and score-band breakdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tests.calibration.run import (
    _aggregate,
    _Fixture,
    _format_report,
    _Outcome,
    _print_failed_outcomes,
)


def _resolve_outcomes_path(fixtures: Path | None, outcomes: Path | None) -> Path:
    """
    Pick which outcomes file to summarize.

    Mirrors `_resolve_retry_outcomes_path`'s precedence: explicit
    `--outcomes` wins; otherwise `--fixtures` resolves to
    `<stem>.outcomes.json` (canonical) or `<stem>.outcomes.partial.json`
    (if only partial exists).
    """
    if outcomes is not None:
        if not outcomes.exists():
            msg = f"outcomes file not found: {outcomes}"
            raise FileNotFoundError(msg)
        return outcomes
    if fixtures is None:
        msg = "must supply --fixtures or --outcomes"
        raise ValueError(msg)
    canonical = fixtures.with_suffix(".outcomes.json")
    if canonical.exists():
        return canonical
    partial = fixtures.with_suffix(".outcomes.partial.json")
    if partial.exists():
        return partial
    msg = (
        f"no outcomes file alongside {fixtures} — looked for "
        f"{canonical.name} and {partial.name}"
    )
    raise FileNotFoundError(msg)


def _entry_to_outcome(entry: dict) -> _Outcome:
    """
    Reconstruct an `_Outcome` from a JSON entry for aggregation.

    `_aggregate` only reads the outcome classification fields (error,
    n_candidates, top_correct, top_score, source_name) plus the
    fixture's source-keyed expected dict for grading-by-source. We
    populate just those — diagnostic fields stay at defaults.
    """
    expected = entry.get("expected")
    source = str(entry["source"])
    fixture_expected: dict[str, int] = (
        {source: int(expected)} if expected is not None else {}
    )
    outcome_tag = str(entry.get("outcome", ""))
    if outcome_tag == "correct":
        top_correct: bool | None = True
    elif outcome_tag == "wrong":
        top_correct = False
    else:
        top_correct = None
    return _Outcome(
        fixture=_Fixture(
            file_path=Path(str(entry.get("file", ""))),
            expected=fixture_expected,
            cover_quality=str(entry.get("cover_quality", "thumbnail")),
        ),
        source_name=source,
        top_score=float(entry.get("top_score", 0.0)),
        top_issue_id=entry.get("top_issue_id"),
        top_correct=top_correct,
        n_candidates=int(entry.get("n_candidates", 0)),
        error=entry.get("error"),
        top_metadata_score=entry.get("top_metadata_score"),
        top_cover_score=entry.get("top_cover_score"),
        runner_up_score=entry.get("runner_up_score"),
        hash_providers_supplied=bool(entry.get("hash_providers_supplied", False)),
    )


def summarize(outcomes_path: Path, *, show_misses: bool) -> None:
    """Read `outcomes_path`, aggregate, and print the report."""
    raw = json.loads(outcomes_path.read_text())
    if not isinstance(raw, list):
        msg = f"{outcomes_path}: expected a JSON list of outcomes"
        raise TypeError(msg)
    outcomes = [_entry_to_outcome(entry) for entry in raw]
    print(f"Summarizing {len(outcomes)} outcomes from {outcomes_path}")  # noqa: T201
    reports = _aggregate(outcomes)
    print(_format_report(reports))  # noqa: T201
    if show_misses:
        _print_failed_outcomes(outcomes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help=(
            "Path to fixtures.json. Defaults to summarizing "
            "<fixtures-stem>.outcomes.json (or .outcomes.partial.json)."
        ),
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=None,
        help=(
            "Explicit outcomes file (overrides --fixtures resolution). "
            "Use for labeled experiments (e.g. .outcomes.fast.json)."
        ),
    )
    parser.add_argument(
        "--misses",
        action="store_true",
        help=(
            "After the report, print the same per-miss diagnostic detail "
            "as the live harness — useful for spot-checking the worst "
            "cases across a long chunked run."
        ),
    )
    args = parser.parse_args()

    try:
        outcomes_path = _resolve_outcomes_path(args.fixtures, args.outcomes)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    summarize(outcomes_path, show_misses=args.misses)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
