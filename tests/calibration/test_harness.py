"""
Unit tests for the calibration harness's offline helpers.

These run as part of the regular test suite — only the live-API parts of
the harness are excluded from `pytest`. Loading fixtures, score-banding,
and aggregation should all work without credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.calibration.run import (
    _aggregate,
    _band_for,
    _Fixture,
    _format_report,
    _load_fixtures,
    _Outcome,
)

# --------------------------------------------------------- score banding


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.99, "0.95-1.00 (very high)"),
        (0.95, "0.95-1.00 (very high)"),
        (0.90, "0.85-0.95 (auto-write)"),
        (0.85, "0.85-0.95 (auto-write)"),
        (0.78, "0.70-0.85 (prompt zone)"),
        (0.55, "0.50-0.70 (solo-viable)"),
        (0.40, "0.00-0.50 (below min_confidence)"),
        (0.00, "0.00-0.50 (below min_confidence)"),
    ],
)
def test_band_for_buckets_correctly(score: float, expected: str) -> None:
    assert _band_for(score) == expected


# --------------------------------------------------------- fixture loading


def test_load_fixtures_parses_full_form(tmp_path: Path) -> None:
    fp = tmp_path / "f.json"
    fp.write_text(
        json.dumps(
            [
                {
                    "file": "/some/path.cbz",
                    "metron": 1,
                    "comicvine": 2,
                    "cover_quality": "full",
                }
            ]
        )
    )
    [fixture] = _load_fixtures(fp)
    assert fixture.file_path == Path("/some/path.cbz")
    assert fixture.expected == {"metron": 1, "comicvine": 2}
    assert fixture.cover_quality == "full"


def test_load_fixtures_skips_null_ids(tmp_path: Path) -> None:
    fp = tmp_path / "f.json"
    fp.write_text(
        json.dumps(
            [{"file": "/x.cbz", "metron": null, "comicvine": 7} for null in [None]]
        )
    )
    [fixture] = _load_fixtures(fp)
    assert fixture.expected == {"comicvine": 7}


def test_load_fixtures_expands_tilde(tmp_path: Path) -> None:
    fp = tmp_path / "f.json"
    fp.write_text(json.dumps([{"file": "~/library/x.cbz", "metron": 1}]))
    [fixture] = _load_fixtures(fp)
    assert "~" not in str(fixture.file_path)


def test_load_fixtures_defaults_cover_quality_to_full(tmp_path: Path) -> None:
    fp = tmp_path / "f.json"
    fp.write_text(json.dumps([{"file": "/x.cbz", "metron": 1}]))
    [fixture] = _load_fixtures(fp)
    assert fixture.cover_quality == "full"


def test_load_fixtures_rejects_non_list(tmp_path: Path) -> None:
    fp = tmp_path / "f.json"
    fp.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(TypeError, match="JSON list of fixtures"):
        _load_fixtures(fp)


# ------------------------------------------------------- aggregation


def _outcome(
    *,
    source: str = "metron",
    score: float = 0.9,
    correct: bool | None = True,
    n: int = 5,
    error: str | None = None,
) -> _Outcome:
    return _Outcome(
        fixture=_Fixture(Path("/x.cbz"), {source: 1}, "full"),
        source_name=source,
        top_score=score,
        top_issue_id=1,
        top_correct=correct,
        n_candidates=n,
        error=error,
    )


def test_aggregate_counts_correct_and_wrong() -> None:
    outcomes = [
        _outcome(score=0.99, correct=True),
        _outcome(score=0.92, correct=True),
        _outcome(score=0.88, correct=False),
    ]
    [report] = _aggregate(outcomes).values()
    assert report.correct == 2
    assert report.wrong == 1


def test_aggregate_counts_no_candidates() -> None:
    outcomes = [_outcome(correct=None, n=0)]
    [report] = _aggregate(outcomes).values()
    assert report.no_candidates == 1
    assert report.correct == 0


def test_aggregate_counts_errors() -> None:
    outcomes = [_outcome(error="HTTPError: 502")]
    [report] = _aggregate(outcomes).values()
    assert report.errored == 1


def test_aggregate_buckets_by_band() -> None:
    outcomes = [
        _outcome(score=0.97, correct=True),
        _outcome(score=0.96, correct=True),
        _outcome(score=0.92, correct=True),
        _outcome(score=0.92, correct=False),
    ]
    [report] = _aggregate(outcomes).values()
    very_high = report.by_band["0.95-1.00 (very high)"]
    auto_write = report.by_band["0.85-0.95 (auto-write)"]
    assert very_high == {"correct": 2, "wrong": 0}
    assert auto_write == {"correct": 1, "wrong": 1}


def test_format_report_renders_per_source() -> None:
    outcomes = [
        _outcome(source="metron", score=0.99, correct=True),
        _outcome(source="comicvine", score=0.60, correct=False),
    ]
    text = _format_report(_aggregate(outcomes))
    assert "=== metron ===" in text
    assert "=== comicvine ===" in text
    assert "accuracy on labeled fixtures" in text


# ----------------------------------------------------------- _Heartbeat


def test_heartbeat_prints_periodically(capsys: pytest.CaptureFixture[str]) -> None:
    """Inside the context, the heartbeat fires at the configured interval."""
    import time

    from tests.calibration.run import _Heartbeat

    with _Heartbeat("test:label", interval=0.05):
        time.sleep(0.18)  # enough for ~3 ticks
    captured = capsys.readouterr().out
    # At least one tick fired before exit.
    assert "still working on test:label" in captured


def test_heartbeat_silent_when_quick(capsys: pytest.CaptureFixture[str]) -> None:
    """A fixture finishing within one tick produces no heartbeat output."""
    from tests.calibration.run import _Heartbeat

    with _Heartbeat("test:label", interval=10.0):
        pass  # immediate exit
    captured = capsys.readouterr().out
    assert "still working" not in captured


# ----------------------------------------------------- _print_cost_estimate


class _FakeSource:
    def __init__(self, name: str) -> None:
        self.name = name


def test_cost_estimate_warns_above_cv_hourly_cap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Worst-case CV cost > 200 calls triggers an hours-long warning."""
    from tests.calibration.run import _print_cost_estimate

    # 50 fixtures x 21 calls = 1,050 CV calls = ~5.25 hours worst case.
    _print_cost_estimate(50, [_FakeSource("comicvine")])  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "ComicVine" in out
    assert "wall time" in out


def test_cost_estimate_quiet_for_small_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Small CV runs get pacing-time note, not hours-long warning."""
    from tests.calibration.run import _print_cost_estimate

    # 5 fixtures x 21 = 105 calls < 200 cap.
    _print_cost_estimate(5, [_FakeSource("comicvine")])  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "ComicVine" in out
    # Pacing message, not the wall-time warning.
    assert "1-req/sec floor" in out


def test_cost_estimate_skips_when_no_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.calibration.run import _print_cost_estimate

    _print_cost_estimate(50, [])
    assert capsys.readouterr().out == ""


# --------------------------------------------- outcomes serialize / retry-misses


def _make_fixture(file_path: Path, **expected: int) -> _Fixture:
    return _Fixture(file_path=file_path, expected=expected, cover_quality="full")


def test_classify_outcome_correct() -> None:
    from tests.calibration.run import _classify_outcome

    assert _classify_outcome(_outcome(correct=True)) == "correct"


def test_classify_outcome_wrong() -> None:
    from tests.calibration.run import _classify_outcome

    assert _classify_outcome(_outcome(correct=False)) == "wrong"


def test_classify_outcome_no_candidates() -> None:
    from tests.calibration.run import _classify_outcome

    assert _classify_outcome(_outcome(correct=None, n=0)) == "no_candidates"


def test_classify_outcome_error() -> None:
    from tests.calibration.run import _classify_outcome

    assert _classify_outcome(_outcome(error="boom")) == "error"


def test_classify_outcome_no_expected_id() -> None:
    """Candidates returned but the fixture didn't list an expected id for this source."""
    from tests.calibration.run import _classify_outcome

    o = _Outcome(
        fixture=_Fixture(Path("/x.cbz"), {}, "full"),
        source_name="metron",
        top_score=0.9,
        top_issue_id=42,
        top_correct=None,
        n_candidates=3,
    )
    assert _classify_outcome(o) == "no_expected_id"


def test_serialize_and_load_round_trip(tmp_path: Path) -> None:
    """Outcomes serialize → deserialize back into the miss-files set we expect."""
    import json as _json

    from tests.calibration.run import _load_miss_files, _serialize_outcomes

    outcomes = [
        _Outcome(
            fixture=_make_fixture(Path("/a.cbz"), metron=1),
            source_name="metron",
            top_score=0.99,
            top_issue_id=1,
            top_correct=True,
            n_candidates=3,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/b.cbz"), metron=2),
            source_name="metron",
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/c.cbz"), comicvine=3),
            source_name="comicvine",
            top_score=0.86,
            top_issue_id=999,
            top_correct=False,
            n_candidates=5,
        ),
    ]
    out_path = tmp_path / "fixtures.outcomes.json"
    _serialize_outcomes(outcomes, out_path)

    payload = _json.loads(out_path.read_text())
    assert {entry["outcome"] for entry in payload} == {
        "correct",
        "no_candidates",
        "wrong",
    }

    misses = _load_miss_files(out_path)
    # /a was correct → omitted. /b (no_candidates) and /c (wrong) → kept.
    assert misses == {"/b.cbz", "/c.cbz"}


def test_filter_to_misses_keeps_only_listed_files(tmp_path: Path) -> None:
    from tests.calibration.run import _filter_to_misses

    f_a = _make_fixture(tmp_path / "a.cbz")
    f_b = _make_fixture(tmp_path / "b.cbz")
    f_c = _make_fixture(tmp_path / "c.cbz")
    miss_files = {str(tmp_path / "a.cbz"), str(tmp_path / "c.cbz")}
    out = _filter_to_misses([f_a, f_b, f_c], miss_files)
    assert out == [f_a, f_c]


def test_load_miss_files_handles_a_comic_with_one_correct_one_wrong(
    tmp_path: Path,
) -> None:
    """A comic where metron correct + cv wrong → kept (we want to retry the cv side)."""
    import json as _json

    out_path = tmp_path / "outcomes.json"
    out_path.write_text(
        _json.dumps(
            [
                {"file": "/x.cbz", "source": "metron", "outcome": "correct"},
                {"file": "/x.cbz", "source": "comicvine", "outcome": "wrong"},
            ]
        )
    )
    from tests.calibration.run import _load_miss_files

    assert _load_miss_files(out_path) == {"/x.cbz"}


# --------------------------------------------- _series_key / --one-per-series


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        pytest.param("Watchmen (1986) #002.cbz", "Watchmen (1986)", id="year-paren"),
        pytest.param("Conan (2004) #005.cbz", "Conan (2004)", id="year-paren-2"),
        pytest.param("Lois Lane (2019) #001.cbz", "Lois Lane (2019)", id="multi-word"),
        pytest.param("Akira (1984) #001.cbz", "Akira (1984)", id="single-word"),
        pytest.param("X-Men Hellfire Gala #001.cbz", "X-Men Hellfire Gala", id="no-paren"),
        # Edge: leading whitespace, multiple spaces
        pytest.param("Foo Bar   #042.cbz", "Foo Bar", id="extra-whitespace"),
        # No issue marker at all → whole filename
        pytest.param("comic.cbz", "comic.cbz", id="no-issue-marker"),
    ],
)
def test_series_key(filename: str, expected: str) -> None:
    from tests.calibration.run import _series_key

    assert _series_key(filename) == expected


def test_dedupe_one_per_series_keeps_first(tmp_path: Path) -> None:
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Watchmen (1986) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Watchmen (1986) #002.cbz", {}, "full"),
        _Fixture(tmp_path / "Watchmen (1986) #003.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #002.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert len(deduped) == 2
    assert deduped[0].file_path.name == "Watchmen (1986) #001.cbz"
    assert deduped[1].file_path.name == "Lois Lane (2019) #001.cbz"


def test_dedupe_one_per_series_distinguishes_volumes(tmp_path: Path) -> None:
    """Lois Lane (1986) and Lois Lane (2019) are separate series — keep both."""
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Lois Lane (1986) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #001.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert len(deduped) == 2


def test_dedupe_one_per_series_preserves_input_order(tmp_path: Path) -> None:
    """Iteration order matches input order (not alphabetical or anything)."""
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Z Series #001.cbz", {}, "full"),
        _Fixture(tmp_path / "A Series #001.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert [f.file_path.name for f in deduped] == [
        "Z Series #001.cbz",
        "A Series #001.cbz",
    ]
