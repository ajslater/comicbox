"""
Calibration-harness tests: top-K MISS diagnostics + per-candidate breakdown.

Split from test_harness.py to keep per-file maintainability index healthy.
The shared `_outcome` / `_make_miss_outcome_with_candidates` factories live
in ``tests.calibration._harness_helpers``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from tests.calibration._harness_helpers import (
    make_miss_outcome_with_candidates,
    make_outcome,
)
from tests.calibration.run import _Fixture, _Outcome

if TYPE_CHECKING:
    import pytest

_outcome = make_outcome
_make_miss_outcome_with_candidates = make_miss_outcome_with_candidates


# --------------------------------------- top-K candidate diagnostic table


def test_print_failed_outcomes_shows_top_candidates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MISS lines list the top-K candidates with breakdowns."""
    from tests.calibration.run import _print_failed_outcomes

    # Watchmen-shaped: top is wrong, runner-up is right, tied scores.
    outcome = _make_miss_outcome_with_candidates(
        [
            (476696, 0.89, 0.91, 0.81),  # wrong, tied
            (27650, 0.89, 0.91, 0.81),  # right, tied at rank 2
            (12345, 0.70, 0.85, 0.40),  # also-ran
        ],
        expected=27650,
    )
    _print_failed_outcomes([outcome])
    out = capsys.readouterr().out
    assert "top candidates:" in out
    # The expected id is flagged with an arrow.
    assert "id=27650" in out
    assert "← expected" in out
    # Per-candidate breakdown is visible.
    assert "md=0.91" in out
    assert "cover=0.81" in out
    # Rank-3 also-ran appears.
    assert "id=12345" in out


def test_print_failed_outcomes_marks_expected_only_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The ← expected marker appears once and on the right line."""
    from tests.calibration.run import _print_failed_outcomes

    outcome = _make_miss_outcome_with_candidates(
        [
            (100, 0.95, 0.95, 0.90),  # top, wrong
            (200, 0.80, 0.80, 0.50),  # right, rank 2
        ],
        expected=200,
    )
    _print_failed_outcomes([outcome])
    out = capsys.readouterr().out
    # Exactly one expected marker.
    assert out.count("← expected") == 1
    # The marker is on the right line (after id=200).
    expected_line = next(line for line in out.splitlines() if "id=200" in line)
    assert "← expected" in expected_line


def test_print_failed_outcomes_handles_missing_cover(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Candidates with no cover_score render as N/A, not 0.00."""
    from tests.calibration.run import _print_failed_outcomes

    outcome = _make_miss_outcome_with_candidates(
        [(100, 0.85, 0.85, None), (200, 0.80, 0.80, None)],
        expected=200,
    )
    _print_failed_outcomes([outcome])
    out = capsys.readouterr().out
    assert "cover=N/A" in out
    assert "cover=0.00" not in out


def test_serialize_includes_top_candidates(tmp_path: Path) -> None:
    """top_candidates breakdowns survive the JSON round-trip."""
    from tests.calibration.run import _serialize_outcomes

    outcome = _make_miss_outcome_with_candidates(
        [
            (476696, 0.89, 0.91, 0.81),
            (27650, 0.89, 0.91, 0.81),
        ],
        expected=27650,
    )
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes([outcome], out_path)
    [entry] = json.loads(out_path.read_text())
    assert len(entry["top_candidates"]) == 2
    assert entry["top_candidates"][0]["issue_id"] == 476696
    assert entry["top_candidates"][1]["issue_id"] == 27650
    assert entry["top_candidates"][0]["cover_score"] == 0.81


def test_serialize_top_candidates_empty_for_no_candidates(tmp_path: Path) -> None:
    """Outcomes with no candidates serialize an empty top_candidates list."""
    from tests.calibration.run import _serialize_outcomes

    outcomes = [_outcome(correct=None, n=0)]
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes(outcomes, out_path)
    [entry] = json.loads(out_path.read_text())
    assert entry["top_candidates"] == []


def test_print_failed_outcomes_includes_series_and_year(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Volume name + cover_year appear in the top-K table for forensics."""
    from tests.calibration.run import _CandidateSummary, _print_failed_outcomes

    summaries = [
        _CandidateSummary(
            issue_id=476696,
            score=0.89,
            metadata_score=0.91,
            cover_score=0.81,
            series="Watchmen Annotated",
            summary_year=1987,
        ),
        _CandidateSummary(
            issue_id=27650,
            score=0.89,
            metadata_score=0.91,
            cover_score=0.81,
            series="Watchmen",
            summary_year=1987,
        ),
    ]
    outcome = _Outcome(
        fixture=_Fixture(Path("/Watchmen #5.cbz"), {"comicvine": 27650}, "full"),
        source_name="comicvine",
        top_score=0.89,
        top_issue_id=476696,
        top_correct=False,
        n_candidates=2,
        top_metadata_score=0.91,
        top_cover_score=0.81,
        runner_up_score=0.89,
        hash_providers_supplied=True,
        top_candidates=summaries,
    )
    _print_failed_outcomes([outcome])
    out = capsys.readouterr().out
    # The volume names appear in the per-candidate breakdown.
    assert "Watchmen Annotated" in out
    assert "Watchmen" in out  # exact-match volume
    # The year is attached to the volume label.
    assert "1987" in out


def test_format_candidate_line_omits_series_when_empty() -> None:
    """Candidates without a series name don't print a bare `[]`."""
    from tests.calibration.run import _CandidateSummary, _format_candidate_line

    c = _CandidateSummary(
        issue_id=1,
        score=0.9,
        metadata_score=0.9,
        cover_score=None,
        series="",
        summary_year=None,
    )
    line = _format_candidate_line(1, c, expected=2)
    assert "[]" not in line
    # The base id/score representation still appears.
    assert "id=1" in line


def test_format_candidate_line_includes_volume_id() -> None:
    """volume_id appears in the bracketed series tag for same-vs-different forensics."""
    from tests.calibration.run import _CandidateSummary, _format_candidate_line

    c = _CandidateSummary(
        issue_id=476696,
        score=0.89,
        metadata_score=0.91,
        cover_score=0.81,
        series="Watchmen",
        summary_year=1987,
        volume_id=10455,
    )
    line = _format_candidate_line(1, c, expected=27650)
    assert "vol=10455" in line
    # The series and year still show.
    assert "Watchmen" in line
    assert "1987" in line


def test_format_candidate_line_omits_volume_when_unset() -> None:
    """When the source doesn't expose volume_id, no `vol=` shows."""
    from tests.calibration.run import _CandidateSummary, _format_candidate_line

    c = _CandidateSummary(
        issue_id=1,
        score=0.9,
        metadata_score=0.9,
        cover_score=None,
        series="Foo",
        summary_year=2020,
        volume_id=None,
    )
    line = _format_candidate_line(1, c, expected=2)
    assert "vol=" not in line
    # Series + year do appear.
    assert "[Foo, 2020]" in line


def test_serialize_top_candidates_includes_volume_id(tmp_path: Path) -> None:
    """volume_id round-trips through outcomes JSON for post-hoc analysis."""
    from tests.calibration.run import _CandidateSummary, _serialize_outcomes

    summaries = [
        _CandidateSummary(
            issue_id=476696,
            score=0.89,
            metadata_score=0.91,
            cover_score=0.81,
            series="Watchmen",
            summary_year=1987,
            volume_id=10455,
        ),
    ]
    outcome = _Outcome(
        fixture=_Fixture(Path("/x.cbz"), {"comicvine": 27650}, "full"),
        source_name="comicvine",
        top_score=0.89,
        top_issue_id=476696,
        top_correct=False,
        n_candidates=1,
        top_candidates=summaries,
    )
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes([outcome], out_path)
    [entry] = json.loads(out_path.read_text())
    assert entry["top_candidates"][0]["volume_id"] == 10455
