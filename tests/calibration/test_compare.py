"""Tests for the calibration outcomes-comparison tool."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _outcome_entry(
    file_path: str,
    source: str,
    outcome: str,
    *,
    top_issue_id: int | None = None,
    top_score: float = 0.0,
    api_call_counts: dict[str, int] | None = None,
) -> dict:
    """Build one entry in the outcomes-JSON shape."""
    return {
        "file": file_path,
        "source": source,
        "outcome": outcome,
        "top_score": top_score,
        "top_issue_id": top_issue_id,
        "expected": 1,
        "n_candidates": 3 if outcome != "no_candidates" else 0,
        "error": None,
        "top_metadata_score": None,
        "top_cover_score": None,
        "runner_up_score": None,
        "hash_providers_supplied": False,
        "top_candidates": [],
        "api_call_counts": api_call_counts or {},
    }


def _write(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


# --------------------------------------------------------- _flip_category


def test_flip_category_wrong_to_correct_is_win() -> None:
    from tests.calibration.compare import _flip_category

    assert _flip_category("wrong", "correct") == "WIN"
    assert _flip_category("no_candidates", "correct") == "WIN"
    assert _flip_category("error", "correct") == "WIN"


def test_flip_category_correct_to_wrong_is_regress() -> None:
    from tests.calibration.compare import _flip_category

    assert _flip_category("correct", "wrong") == "REGRESS"
    assert _flip_category("correct", "no_candidates") == "REGRESS"
    assert _flip_category("correct", "error") == "REGRESS"


def test_flip_category_no_change_returns_none() -> None:
    from tests.calibration.compare import _flip_category

    assert _flip_category("correct", "correct") is None
    assert _flip_category("wrong", "wrong") is None


def test_flip_category_wiggle_between_failures_is_neutral() -> None:
    from tests.calibration.compare import _flip_category

    assert _flip_category("wrong", "no_candidates") == "NEUTRAL"
    assert _flip_category("error", "wrong") == "NEUTRAL"


# --------------------------------------------------------- _compute_flips


def test_compute_flips_emits_each_changed_pair() -> None:
    from tests.calibration.compare import _compute_flips

    before = {
        ("/a.cbz", "comicvine"): _outcome_entry("/a.cbz", "comicvine", "wrong"),
        ("/b.cbz", "comicvine"): _outcome_entry("/b.cbz", "comicvine", "correct"),
        ("/c.cbz", "comicvine"): _outcome_entry("/c.cbz", "comicvine", "no_candidates"),
    }
    after = {
        ("/a.cbz", "comicvine"): _outcome_entry(
            "/a.cbz", "comicvine", "correct"
        ),  # WIN
        ("/b.cbz", "comicvine"): _outcome_entry(
            "/b.cbz", "comicvine", "wrong"
        ),  # REGRESS
        ("/c.cbz", "comicvine"): _outcome_entry(
            "/c.cbz", "comicvine", "no_candidates"
        ),  # no flip
    }
    flips = _compute_flips(before, after)
    categories = {category for category, _, _, _ in flips}
    assert categories == {"WIN", "REGRESS"}
    # No flip emitted for unchanged outcomes.
    assert len(flips) == 2


# --------------------------------------------------------- _sum_call_counts


def test_sum_call_counts_aggregates_across_entries() -> None:
    from tests.calibration.compare import _sum_call_counts

    entries = [
        _outcome_entry(
            "/a.cbz",
            "comicvine",
            "correct",
            api_call_counts={"search_volumes": 1, "list_issues": 5},
        ),
        _outcome_entry(
            "/b.cbz",
            "comicvine",
            "correct",
            api_call_counts={"search_volumes": 1, "list_issues": 7},
        ),
        _outcome_entry("/c.cbz", "comicvine", "correct"),  # no counts
    ]
    assert _sum_call_counts(entries) == {"search_volumes": 2, "list_issues": 12}


# --------------------------------------------------------- _aggregate


def test_aggregate_buckets_per_outcome_tag() -> None:
    from tests.calibration.compare import _aggregate

    entries = [
        _outcome_entry("/a.cbz", "comicvine", "correct"),
        _outcome_entry("/b.cbz", "comicvine", "correct"),
        _outcome_entry("/c.cbz", "comicvine", "wrong"),
        _outcome_entry("/d.cbz", "comicvine", "no_candidates"),
    ]
    assert _aggregate(entries) == {"correct": 2, "wrong": 1, "no_candidates": 1}


# --------------------------------------------------------- _load


def test_load_indexes_by_file_and_source(tmp_path: Path) -> None:
    from tests.calibration.compare import _load

    path = tmp_path / "outcomes.json"
    _write(
        path,
        [
            _outcome_entry("/x.cbz", "metron", "correct"),
            _outcome_entry("/x.cbz", "comicvine", "wrong"),
        ],
    )
    loaded = _load(path)
    assert ("/x.cbz", "metron") in loaded
    assert ("/x.cbz", "comicvine") in loaded
    assert loaded[("/x.cbz", "metron")]["outcome"] == "correct"


# --------------------------------------------------------- main, end-to-end


def test_main_diffs_two_files_with_wins_and_regressions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: writes two outcome files, runs main, expects flips printed."""
    import sys

    from tests.calibration.compare import main

    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write(
        before_path,
        [
            _outcome_entry(
                "/won.cbz",
                "comicvine",
                "wrong",
                api_call_counts={"search_volumes": 1, "list_issues": 9},
            ),
            _outcome_entry(
                "/lost.cbz",
                "comicvine",
                "correct",
                api_call_counts={"search_volumes": 1, "list_issues": 8},
            ),
        ],
    )
    _write(
        after_path,
        [
            _outcome_entry(
                "/won.cbz",
                "comicvine",
                "correct",
                api_call_counts={"search_volumes": 1, "list_issues": 3},
            ),
            _outcome_entry(
                "/lost.cbz",
                "comicvine",
                "wrong",
                api_call_counts={"search_volumes": 1, "list_issues": 3},
            ),
        ],
    )

    argv_saved = sys.argv
    sys.argv = ["compare.py", str(before_path), str(after_path)]
    try:
        ret = main()
    finally:
        sys.argv = argv_saved
    assert ret == 0
    out = capsys.readouterr().out
    # Aggregate counts surface.
    assert "baseline" in out.lower()
    assert "candidate" in out.lower()
    # Both flip categories appear.
    assert "WIN" in out
    assert "REGRESS" in out
    # Call totals appear (the cost side).
    assert "api calls" in out.lower()
    # Per-fixture lines name the files.
    assert "won.cbz" in out
    assert "lost.cbz" in out


def test_main_reports_no_flips_when_files_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When before == after, output explicitly says no flips."""
    import sys

    from tests.calibration.compare import main

    path = tmp_path / "x.json"
    entries = [_outcome_entry("/a.cbz", "comicvine", "correct")]
    _write(path, entries)

    other = tmp_path / "y.json"
    _write(other, entries)

    argv_saved = sys.argv
    sys.argv = ["compare.py", str(path), str(other)]
    try:
        ret = main()
    finally:
        sys.argv = argv_saved
    assert ret == 0
    out = capsys.readouterr().out
    assert "No per-fixture flips" in out


def test_main_errors_when_baseline_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing baseline file → returns 1, error on stderr."""
    import sys

    from tests.calibration.compare import main

    after = tmp_path / "after.json"
    _write(after, [])
    missing = tmp_path / "missing.json"

    argv_saved = sys.argv
    sys.argv = ["compare.py", str(missing), str(after)]
    try:
        ret = main()
    finally:
        sys.argv = argv_saved
    assert ret == 1
    err = capsys.readouterr().err
    assert "baseline not found" in err
