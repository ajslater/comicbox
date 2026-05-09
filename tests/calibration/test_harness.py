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
