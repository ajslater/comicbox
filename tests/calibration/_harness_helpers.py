"""Shared test factories for the calibration-harness test suite."""

from __future__ import annotations

import json
from pathlib import Path

from tests.calibration.run import _Fixture, _Outcome


def make_outcome(  # noqa: PLR0913
    *,
    source: str = "metron",
    score: float = 0.9,
    correct: bool | None = True,
    n: int = 5,
    error: str | None = None,
    top_metadata_score: float | None = None,
    top_cover_score: float | None = None,
    runner_up_score: float | None = None,
    hash_providers_supplied: bool = False,
    api_call_counts: dict[str, int] | None = None,
) -> _Outcome:
    return _Outcome(
        fixture=_Fixture(Path("/x.cbz"), {source: 1}, "full"),
        source_name=source,
        top_score=score,
        top_issue_id=1,
        top_correct=correct,
        n_candidates=n,
        error=error,
        top_metadata_score=top_metadata_score,
        top_cover_score=top_cover_score,
        runner_up_score=runner_up_score,
        hash_providers_supplied=hash_providers_supplied,
        api_call_counts=api_call_counts or {},
    )


def make_fixture(file_path: Path, **expected: int) -> _Fixture:
    return _Fixture(file_path=file_path, expected=expected, cover_quality="full")


def write_outcomes(path: Path, file_path: str, outcome: str) -> None:
    """Write a one-entry outcomes file for retry-fallback tests."""
    path.write_text(
        json.dumps(
            [
                {
                    "file": file_path,
                    "source": "metron",
                    "outcome": outcome,
                    "top_score": 0.0,
                    "top_issue_id": None,
                    "expected": 1,
                    "n_candidates": 0,
                    "error": None,
                }
            ]
        )
    )


def make_miss_outcome_with_candidates(
    candidates: list[tuple[int, float, float, float | None]],
    *,
    expected: int,
) -> _Outcome:
    """Build a MISS _Outcome with the given (id, score, md, cover) candidates."""
    from tests.calibration.run import _CandidateSummary

    summaries = [
        _CandidateSummary(issue_id=cid, score=s, metadata_score=md, cover_score=cs)
        for cid, s, md, cs in candidates
    ]
    top = summaries[0]
    runner = summaries[1] if len(summaries) > 1 else None
    return _Outcome(
        fixture=_Fixture(Path("/Watchmen #5.cbz"), {"comicvine": expected}, "full"),
        source_name="comicvine",
        top_score=top.score,
        top_issue_id=top.issue_id,
        top_correct=False,
        n_candidates=len(summaries),
        top_metadata_score=top.metadata_score,
        top_cover_score=top.cover_score,
        runner_up_score=runner.score if runner else None,
        hash_providers_supplied=True,
        top_candidates=summaries,
    )
