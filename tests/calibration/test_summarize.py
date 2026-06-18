"""Unit tests for the cumulative-outcomes summarizer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tests.calibration.summarize import (
    _entry_to_outcome,
    _resolve_outcomes_path,
    summarize,
)

if TYPE_CHECKING:
    from pathlib import Path


# --- _resolve_outcomes_path ---


def test_resolve_outcomes_explicit_wins(tmp_path: Path) -> None:
    """--outcomes always overrides --fixtures resolution."""
    fp = tmp_path / "fixtures.json"
    explicit = tmp_path / "custom.outcomes.json"
    explicit.write_text("[]")
    assert _resolve_outcomes_path(fp, explicit) == explicit


def test_resolve_outcomes_explicit_missing_errors(tmp_path: Path) -> None:
    """--outcomes pointing at a non-existent file is an error."""
    with pytest.raises(FileNotFoundError, match="not found"):
        _resolve_outcomes_path(None, tmp_path / "nope.json")


def test_resolve_outcomes_prefers_canonical(tmp_path: Path) -> None:
    """When both canonical and partial exist, canonical wins."""
    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    canonical.write_text("[]")
    partial.write_text("[]")
    assert _resolve_outcomes_path(fp, None) == canonical


def test_resolve_outcomes_falls_back_to_partial(tmp_path: Path) -> None:
    """No canonical → use partial (the user's only iteration data)."""
    fp = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    partial.write_text("[]")
    assert _resolve_outcomes_path(fp, None) == partial


def test_resolve_outcomes_raises_when_nothing_exists(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no outcomes file"):
        _resolve_outcomes_path(tmp_path / "fixtures.json", None)


def test_resolve_outcomes_requires_one_of_two_args() -> None:
    with pytest.raises(ValueError, match="--fixtures or --outcomes"):
        _resolve_outcomes_path(None, None)


# --- _entry_to_outcome ---


def test_entry_to_outcome_correct() -> None:
    entry = {
        "file": "/a.cbz",
        "source": "metron",
        "outcome": "correct",
        "top_score": 0.95,
        "top_issue_id": 42,
        "expected": 42,
        "n_candidates": 3,
        "error": None,
    }
    o = _entry_to_outcome(entry)
    assert o.top_correct is True
    assert o.fixture.expected == {"metron": 42}
    assert o.top_score == pytest.approx(0.95)


def test_entry_to_outcome_wrong() -> None:
    entry = {
        "file": "/a.cbz",
        "source": "metron",
        "outcome": "wrong",
        "top_score": 0.88,
        "top_issue_id": 99,
        "expected": 42,
        "n_candidates": 2,
        "error": None,
    }
    assert _entry_to_outcome(entry).top_correct is False


def test_entry_to_outcome_no_expected_id_is_none() -> None:
    """A fixture without an expected id → top_correct=None (ungradeable)."""
    entry = {
        "file": "/a.cbz",
        "source": "metron",
        "outcome": "no_expected_id",
        "top_score": 0.9,
        "top_issue_id": 42,
        "expected": None,
        "n_candidates": 5,
        "error": None,
    }
    o = _entry_to_outcome(entry)
    assert o.top_correct is None
    assert o.fixture.expected == {}


def test_entry_to_outcome_errored_carries_error_string() -> None:
    entry = {
        "file": "/a.cbz",
        "source": "comicvine",
        "outcome": "error",
        "top_score": 0.0,
        "top_issue_id": None,
        "expected": 1,
        "n_candidates": 0,
        "error": "HTTPError: 502",
    }
    assert _entry_to_outcome(entry).error == "HTTPError: 502"


# --- summarize (end-to-end) ---


def _write_outcomes(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


def test_summarize_aggregates_across_chunks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Across multiple chunks' worth of outcomes, totals appear in one report."""
    outcomes = tmp_path / "f.outcomes.json"
    _write_outcomes(
        outcomes,
        [
            {
                "file": "/a.cbz",
                "source": "metron",
                "outcome": "correct",
                "top_score": 0.95,
                "expected": 1,
                "n_candidates": 3,
                "error": None,
            },
            {
                "file": "/b.cbz",
                "source": "metron",
                "outcome": "wrong",
                "top_score": 0.88,
                "expected": 2,
                "n_candidates": 2,
                "error": None,
            },
            {
                "file": "/c.cbz",
                "source": "comicvine",
                "outcome": "correct",
                "top_score": 0.92,
                "expected": 3,
                "n_candidates": 1,
                "error": None,
            },
        ],
    )

    summarize(outcomes, show_misses=False)
    out = capsys.readouterr().out
    assert "Summarizing 3 outcomes" in out
    assert "=== metron ===" in out
    assert "=== comicvine ===" in out
    # Per-source totals visible
    assert "accuracy on labeled fixtures: 50.0%" in out  # metron 1/2
    assert "accuracy on labeled fixtures: 100.0%" in out  # cv 1/1


def test_summarize_misses_flag_prints_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--misses surfaces the per-failure detail block from the live harness."""
    outcomes = tmp_path / "f.outcomes.json"
    _write_outcomes(
        outcomes,
        [
            {
                "file": "/wrong.cbz",
                "source": "metron",
                "outcome": "wrong",
                "top_score": 0.85,
                "top_issue_id": 9,
                "expected": 1,
                "n_candidates": 2,
                "error": None,
            },
        ],
    )
    summarize(outcomes, show_misses=True)
    out = capsys.readouterr().out
    assert "Outcomes worth a look" in out
    assert "[MISS] metron" in out
    assert "expected=1 got=9" in out


def test_summarize_misses_flag_omitted_skips_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --misses, only the aggregate report prints."""
    outcomes = tmp_path / "f.outcomes.json"
    _write_outcomes(
        outcomes,
        [
            {
                "file": "/wrong.cbz",
                "source": "metron",
                "outcome": "wrong",
                "top_score": 0.85,
                "expected": 1,
                "n_candidates": 2,
                "error": None,
            },
        ],
    )
    summarize(outcomes, show_misses=False)
    out = capsys.readouterr().out
    assert "Outcomes worth a look" not in out


def test_summarize_rejects_non_list(tmp_path: Path) -> None:
    outcomes = tmp_path / "bad.outcomes.json"
    outcomes.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(TypeError, match="JSON list of outcomes"):
        summarize(outcomes, show_misses=False)


def test_summarize_empty_list_is_a_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outcomes = tmp_path / "f.outcomes.json"
    outcomes.write_text("[]")
    summarize(outcomes, show_misses=False)
    # Just prints the "Summarizing 0 outcomes" line; no per-source blocks.
    out = capsys.readouterr().out
    assert "Summarizing 0 outcomes" in out
    assert "===" not in out
