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


def _outcome(  # noqa: PLR0913
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


# ------------------------------------------------------ _ETA + _format_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        pytest.param(0.0, "0s", id="zero"),
        pytest.param(7.4, "7s", id="under-minute-short"),
        pytest.param(59.9, "60s", id="just-under-minute"),
        pytest.param(60.0, "1.0m", id="one-minute"),
        pytest.param(150.0, "2.5m", id="two-and-a-half-minutes"),
        pytest.param(3599.0, "60.0m", id="just-under-hour"),
        pytest.param(3600.0, "1.0h", id="one-hour"),
        pytest.param(86_399.0, "24.0h", id="just-under-day"),
        pytest.param(86_400.0, "1.0d", id="one-day"),
        pytest.param(259_200.0, "3.0d", id="three-days"),
    ],
)
def test_format_duration_units(seconds: float, expected: str) -> None:
    from tests.calibration.run import _format_duration

    assert _format_duration(seconds) == expected


def test_eta_starts_without_estimate() -> None:
    """Before any fixture completes, eta_seconds is None (no data to project)."""
    from tests.calibration.run import _ETA

    eta = _ETA(total_fixtures=100)
    assert eta.eta_seconds() is None
    assert eta.remaining() == 100


def test_eta_projects_after_first_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """One fixture's duration extrapolates to the whole remaining count."""
    import time as _time

    from tests.calibration.run import _ETA

    fake_now = [1_000.0]

    def _fake_monotonic() -> float:
        return fake_now[0]

    monkeypatch.setattr(_time, "monotonic", _fake_monotonic)
    eta = _ETA(total_fixtures=10)
    eta.fixture_started()
    fake_now[0] += 60.0  # one fixture took 60 seconds
    eta.fixture_finished()
    assert eta.remaining() == 9
    # Average is 60s; 9 remaining → 540s ETA.
    assert eta.eta_seconds() == pytest.approx(540.0)


def test_eta_rolling_average_responds_to_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ETA tracks the rolling window — recent slow fixtures inflate it."""
    import time as _time

    from tests.calibration.run import _ETA

    fake_now = [0.0]
    monkeypatch.setattr(_time, "monotonic", lambda: fake_now[0])
    eta = _ETA(total_fixtures=100)
    # Fast warm-up: 10 fixtures at 1s each.
    for _ in range(10):
        eta.fixture_started()
        fake_now[0] += 1.0
        eta.fixture_finished()
    # Hit rate-limit wall: 1 fixture at 600s.
    eta.fixture_started()
    fake_now[0] += 600.0
    eta.fixture_finished()
    # Average over the rolling window (last 11 fixtures): (10*1 + 600) / 11 ≈ 55s.
    avg_per_fixture = eta.eta_seconds() / eta.remaining()  # type: ignore[operator]
    assert 50.0 < avg_per_fixture < 60.0


def test_eta_progress_line_includes_elapsed_and_eta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`progress_line()` returns the compact format used by the heartbeat."""
    import time as _time

    from tests.calibration.run import _ETA

    fake_now = [0.0]
    monkeypatch.setattr(_time, "monotonic", lambda: fake_now[0])
    eta = _ETA(total_fixtures=4)
    eta.fixture_started()
    fake_now[0] += 30.0
    eta.fixture_finished()
    line = eta.progress_line()
    assert "1/4 fixtures" in line
    assert "elapsed" in line
    assert "ETA" in line


def test_eta_no_eta_when_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once all fixtures done, eta_seconds returns None (no more work)."""
    import time as _time

    from tests.calibration.run import _ETA

    fake_now = [0.0]
    monkeypatch.setattr(_time, "monotonic", lambda: fake_now[0])
    eta = _ETA(total_fixtures=2)
    for _ in range(2):
        eta.fixture_started()
        fake_now[0] += 1.0
        eta.fixture_finished()
    assert eta.remaining() == 0
    assert eta.eta_seconds() is None


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
        pytest.param(
            "X-Men Hellfire Gala #001.cbz", "X-Men Hellfire Gala", id="no-paren"
        ),
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


# --------------------------------------------- _hash_providers / cover-quality gating


class _FakeBox:
    """Minimal stand-in for a Comicbox instance — just enough for _hash_providers."""

    def _local_cover_phash(self) -> str | None:
        return "deadbeef"

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        return f"hash:{url}"


def test_hash_providers_full_returns_methods() -> None:
    """cover_quality='full' wires both providers as callables bound to the box."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "full")
    local, fetcher = _hash_providers(_FakeBox(), fixture)
    # Python creates a fresh bound-method object per attribute access, so
    # `is` comparison won't work — verify behavior instead.
    assert local is not None
    assert fetcher is not None
    assert callable(local)
    assert callable(fetcher)


def test_hash_providers_thumbnail_returns_none() -> None:
    """Slimlib (downscaled-cover) fixtures stay metadata-only."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "thumbnail")
    assert _hash_providers(_FakeBox(), fixture) == (None, None)


def test_hash_providers_missing_returns_none() -> None:
    """Cover-missing fixtures can't contribute to the hash signal."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "missing")
    assert _hash_providers(_FakeBox(), fixture) == (None, None)


def test_hash_providers_call_through_returns_box_results() -> None:
    """The returned callables actually invoke the box's methods."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "full")
    local, fetcher = _hash_providers(_FakeBox(), fixture)
    assert local is not None
    assert fetcher is not None
    assert local() == "deadbeef"
    assert fetcher("https://example.test/cover.jpg") == (
        "hash:https://example.test/cover.jpg"
    )


# --------------------------------------- _resolve_retry_outcomes_path fallback


def _write_outcomes(path: Path, file_path: str, outcome: str) -> None:
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


def test_resolve_retry_outcomes_prefers_full(tmp_path: Path) -> None:
    """When both files exist, full takes precedence (canonical source)."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    full = tmp_path / "fixtures.outcomes.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(full, "/a.cbz", "wrong")
    _write_outcomes(partial, "/b.cbz", "wrong")

    assert _resolve_retry_outcomes_path(fixtures_path) == full


def test_resolve_retry_outcomes_falls_back_to_partial(tmp_path: Path) -> None:
    """No full file → use the partial (the user's only iteration data)."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(partial, "/b.cbz", "wrong")

    assert _resolve_retry_outcomes_path(fixtures_path) == partial


def test_resolve_retry_outcomes_raises_when_neither_exists(tmp_path: Path) -> None:
    """Neither file present → clear error naming both expected paths."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    with pytest.raises(FileNotFoundError, match=r"outcomes\.partial\.json"):
        _resolve_retry_outcomes_path(fixtures_path)


def test_apply_filters_uses_partial_when_full_missing(tmp_path: Path) -> None:
    """End-to-end: --retry-misses with only a partial file filters as expected."""
    from tests.calibration.run import _apply_filters

    fixtures_path = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(partial, "/keep.cbz", "wrong")

    fixtures = [
        _Fixture(Path("/keep.cbz"), {"metron": 1}, "full"),
        _Fixture(Path("/drop.cbz"), {"metron": 2}, "full"),
    ]
    out = _apply_filters(
        fixtures,
        fixtures_path=fixtures_path,
        retry_misses=True,
        name_filter=None,
        one_per_series=False,
        limit=None,
    )
    assert [f.file_path.name for f in out] == ["keep.cbz"]


# --------------------------------------- diagnostic detail / cover-score repr


def test_cover_score_repr_fired() -> None:
    """When hashing produced a score, render it as a float."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.91,
        top_cover_score=0.82,
        runner_up_score=0.80,
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "0.82"


def test_cover_score_repr_quality_gated_off() -> None:
    """cover_quality != full → harness never supplied providers."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.91,
        top_cover_score=None,
        hash_providers_supplied=False,
    )
    assert _cover_score_repr(o) == "N/A (cover_quality != full)"


def test_cover_score_repr_unambiguous_metadata() -> None:
    """Wide gap → matcher's _should_invoke_hashing would have skipped."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.97,
        correct=False,
        top_metadata_score=0.97,
        top_cover_score=None,
        runner_up_score=0.50,  # gap = 0.47
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "N/A (unambiguous metadata)"


def test_cover_score_repr_provider_failure() -> None:
    """Tight gap + None cover_score → hashing fired but couldn't produce."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.89,
        top_cover_score=None,
        runner_up_score=0.85,  # gap = 0.04 < 0.10
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "N/A (provider returned None)"


def test_print_failed_outcomes_includes_diagnostic_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MISS lines show metadata=, cover=, gap= for hand-investigation."""
    from tests.calibration.run import _print_failed_outcomes

    outcomes = [
        _outcome(
            source="comicvine",
            score=0.89,
            correct=False,
            n=9,
            top_metadata_score=0.91,
            top_cover_score=0.82,
            runner_up_score=0.80,
            hash_providers_supplied=True,
        ),
    ]
    _print_failed_outcomes(outcomes)
    out = capsys.readouterr().out
    assert "[MISS] comicvine" in out
    assert "metadata=0.91" in out
    assert "cover=0.82" in out
    assert "gap=0.09" in out  # 0.89 - 0.80


def test_print_failed_outcomes_handles_empty_n(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """EMPTY (n=0) lines don't crash trying to format missing diagnostic fields."""
    from tests.calibration.run import _print_failed_outcomes

    outcomes = [_outcome(correct=None, n=0)]  # no diagnostic fields set
    _print_failed_outcomes(outcomes)
    out = capsys.readouterr().out
    assert "[EMPTY]" in out
    # No diagnostic line for empty cases (top_metadata_score is None).
    assert "metadata=" not in out


def test_print_progress_distinguishes_empty_from_no_expected_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Used to be one conflated message; split for clarity."""
    from tests.calibration.run import _print_progress

    fixture = _Fixture(Path("/x.cbz"), {}, "full")  # no expected ids
    # Case 1: actually returned 0 candidates.
    empty = _outcome(correct=None, n=0)
    # Case 2: 5 candidates returned but fixture has no labeled id.
    no_id = _outcome(correct=None, n=5)

    _print_progress(empty, fixture)
    _print_progress(no_id, fixture)
    out = capsys.readouterr().out

    assert "no candidates returned" in out
    assert "no expected metron id" in out
    assert "n=5" in out


def test_serialize_includes_diagnostic_fields(tmp_path: Path) -> None:
    """Outcomes JSON carries metadata/cover/gap info for post-hoc analysis."""
    from tests.calibration.run import _serialize_outcomes

    outcomes = [
        _outcome(
            source="comicvine",
            score=0.89,
            correct=False,
            top_metadata_score=0.91,
            top_cover_score=0.82,
            runner_up_score=0.80,
            hash_providers_supplied=True,
        ),
    ]
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes(outcomes, out_path)
    payload = json.loads(out_path.read_text())
    [entry] = payload
    assert entry["top_metadata_score"] == 0.91
    assert entry["top_cover_score"] == 0.82
    assert entry["runner_up_score"] == 0.80
    assert entry["hash_providers_supplied"] is True


# --------------------------------------- top-K candidate diagnostic table


def _make_miss_outcome_with_candidates(
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


# --------------------------------------- partial-outcomes merge semantics


def test_merge_writes_fresh_when_file_missing(tmp_path: Path) -> None:
    """First filtered run writes; subsequent ones merge."""
    from tests.calibration.run import _merge_outcomes_to_partial

    path = tmp_path / "fixtures.outcomes.partial.json"
    new_outcomes = [_outcome(source="metron", score=0.99, correct=True)]
    _merge_outcomes_to_partial(path, new_outcomes)
    assert path.exists()
    [entry] = json.loads(path.read_text())
    assert entry["outcome"] == "correct"


def test_merge_preserves_other_fixtures_when_retrying_subset(
    tmp_path: Path,
) -> None:
    """
    The smoking gun: retrying just Watchmen shouldn't wipe Conan's miss.

    This is the bug we shipped: each --retry-misses overwrote the partial
    with just its subset, so successful retries silently destroyed the
    record of which other fixtures were still broken.
    """
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "fixtures.outcomes.partial.json"
    # Existing partial: three misses across three different families.
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/Watchmen.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.89,
            top_issue_id=2,
            top_correct=False,
            n_candidates=3,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/Conan.cbz"), comicvine=10),
            source_name="comicvine",
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/LoisLane.cbz"), comicvine=20),
            source_name="comicvine",
            top_score=0.78,
            top_issue_id=21,
            top_correct=False,
            n_candidates=2,
        ),
    ]
    _serialize_outcomes(existing, path)

    # Retry just Watchmen — it now passes.
    new = [
        _Outcome(
            fixture=_make_fixture(Path("/Watchmen.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.95,
            top_issue_id=1,
            top_correct=True,
            n_candidates=3,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    by_file = {entry["file"]: entry for entry in merged}
    # All three fixtures are still present.
    assert set(by_file) == {"/Watchmen.cbz", "/Conan.cbz", "/LoisLane.cbz"}
    # Watchmen got updated to correct.
    assert by_file["/Watchmen.cbz"]["outcome"] == "correct"
    # The other two are preserved with their original miss outcomes.
    assert by_file["/Conan.cbz"]["outcome"] == "no_candidates"
    assert by_file["/LoisLane.cbz"]["outcome"] == "wrong"


def test_merge_keys_by_file_and_source(tmp_path: Path) -> None:
    """Same file with two sources gets two independent entries."""
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "outcomes.partial.json"
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="metron",
            top_score=0.0,
            top_issue_id=None,
            top_correct=False,
            n_candidates=0,
            error="boom",
        ),
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="comicvine",
            top_score=0.99,
            top_issue_id=2,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _serialize_outcomes(existing, path)

    # Retry just the metron side; it now passes.
    new = [
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="metron",
            top_score=0.97,
            top_issue_id=1,
            top_correct=True,
            n_candidates=3,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    by_key = {(e["file"], e["source"]): e for e in merged}
    # Metron side updated; CV side preserved.
    assert by_key[("/x.cbz", "metron")]["outcome"] == "correct"
    assert by_key[("/x.cbz", "comicvine")]["outcome"] == "correct"
    # No duplicates created.
    assert len(merged) == 2


def test_merge_appends_new_entries(tmp_path: Path) -> None:
    """A fixture not in the existing partial gets appended."""
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "outcomes.partial.json"
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/old.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.0,
            top_issue_id=None,
            top_correct=False,
            n_candidates=0,
        ),
    ]
    _serialize_outcomes(existing, path)

    new = [
        _Outcome(
            fixture=_make_fixture(Path("/new.cbz"), comicvine=2),
            source_name="comicvine",
            top_score=0.95,
            top_issue_id=2,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    files = [e["file"] for e in merged]
    assert files == ["/old.cbz", "/new.cbz"]  # existing first, new appended


def test_merge_preserves_existing_extra_keys(tmp_path: Path) -> None:
    """
    Entries in the existing file that have keys we don't recognize survive.

    Future-proofs the merge against schema additions: if a previous
    `comicbox` version wrote outcome fields we no longer emit, those
    fields stay on un-retried entries. New writes use the current
    schema; existing un-touched entries keep theirs.
    """
    from tests.calibration.run import _merge_outcomes_to_partial

    path = tmp_path / "outcomes.partial.json"
    # Hand-crafted entry with a future-only field.
    path.write_text(
        json.dumps(
            [
                {
                    "file": "/preserved.cbz",
                    "source": "metron",
                    "outcome": "wrong",
                    "top_score": 0.5,
                    "future_field": "kept",
                }
            ]
        )
    )

    new = [
        _Outcome(
            fixture=_make_fixture(Path("/new.cbz"), metron=1),
            source_name="metron",
            top_score=0.99,
            top_issue_id=1,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    preserved = next(e for e in merged if e["file"] == "/preserved.cbz")
    assert preserved["future_field"] == "kept"


# --------------------------------------- api_call_counts diff helper


def test_diff_counts_returns_only_increased_methods() -> None:
    """Per-method delta between two snapshots; only positive increments listed."""
    from tests.calibration.run import _diff_counts

    before = {"search_volumes": 5, "list_issues": 20}
    after = {"search_volumes": 6, "list_issues": 23, "get_issue": 1}
    diff = _diff_counts(before, after)
    # search_volumes: +1, list_issues: +3, get_issue: +1 (was 0).
    assert diff == {"search_volumes": 1, "list_issues": 3, "get_issue": 1}


def test_diff_counts_drops_zero_deltas() -> None:
    """Methods called the same number of times pre and post are omitted."""
    from tests.calibration.run import _diff_counts

    before = {"a": 5, "b": 2}
    after = {"a": 5, "b": 2, "c": 0}
    assert _diff_counts(before, after) == {}


def test_diff_counts_handles_empty_before() -> None:
    """Empty before snapshot (first fixture in a run) → all of after counts."""
    from tests.calibration.run import _diff_counts

    assert _diff_counts({}, {"search_volumes": 1}) == {"search_volumes": 1}


def test_serialize_includes_api_call_counts(tmp_path: Path) -> None:
    """api_call_counts survives the JSON round-trip via _serialize_outcomes."""
    from tests.calibration.run import _serialize_outcomes

    outcome = _outcome(
        api_call_counts={"search_volumes": 1, "list_issues": 7},
    )
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes([outcome], out_path)
    [entry] = json.loads(out_path.read_text())
    assert entry["api_call_counts"] == {"search_volumes": 1, "list_issues": 7}


# --------------------------------------- atomic write + periodic checkpoint


def test_atomic_write_json_leaves_no_temp_file(tmp_path: Path) -> None:
    """After a normal write, no `.tmp` leftover on disk."""
    from tests.calibration.run import _atomic_write_json

    target = tmp_path / "outcomes.json"
    _atomic_write_json(target, [{"file": "/x.cbz"}])
    assert target.exists()
    # No leftover tmp file in the same directory.
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_atomic_write_json_overwrites_existing(tmp_path: Path) -> None:
    """Subsequent writes replace the file content, not append."""
    from tests.calibration.run import _atomic_write_json

    target = tmp_path / "outcomes.json"
    _atomic_write_json(target, [{"k": 1}])
    _atomic_write_json(target, [{"k": 2}])
    assert json.loads(target.read_text()) == [{"k": 2}]


def test_serialize_outcomes_uses_atomic_write(tmp_path: Path) -> None:
    """`_serialize_outcomes` should round-trip even when called twice."""
    from tests.calibration.run import _serialize_outcomes

    target = tmp_path / "outcomes.json"
    _serialize_outcomes([_outcome(score=0.9)], target)
    _serialize_outcomes([_outcome(score=0.8)], target)
    payload = json.loads(target.read_text())
    assert len(payload) == 1
    assert payload[0]["top_score"] == 0.8


def test_calibrate_loop_invokes_checkpoint_every_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `_calibrate_loop` calls the checkpoint callback every Nth fixture.

    Uses a fake source so the loop doesn't hit any real API code paths.
    """
    from tests.calibration.run import _calibrate_loop

    class _NoopSource:
        name = "metron"

        def __init__(self) -> None:
            # Per-instance to satisfy RUF012; matches the production
            # OnlineSource pattern.
            self.api_call_counts: dict[str, int] = {}

        def search(self, profile):
            return []

    # Stub `_score_one` so we don't open Comicbox files — the test is
    # about checkpoint cadence, not about scoring.
    from tests.calibration import run as run_mod

    def _fake_score(source, fixture):
        return _outcome(source=source.name, correct=True)

    monkeypatch.setattr(run_mod, "_score_one", _fake_score)

    # 25 fixtures that "exist" via a real tmp_path/touch dance.
    # We can sidestep the missing-file branch by patching `Path.exists`
    # to always return True.
    monkeypatch.setattr(Path, "exists", lambda self: True)  # noqa: ARG005

    fixtures = [_Fixture(Path(f"/x{i}.cbz"), {"metron": i}, "full") for i in range(25)]
    checkpoints: list[int] = []

    def _capture(outcomes: list) -> None:
        checkpoints.append(len(outcomes))

    _calibrate_loop(
        fixtures,
        [_NoopSource()],  # type: ignore[list-item]
        checkpoint=_capture,
        checkpoint_every=10,
    )
    # 25 fixtures, checkpoint every 10 → fires at fixture 10 and 20.
    # Fixture 25 doesn't trigger (25 % 10 != 0). Each checkpoint sees
    # the outcomes-so-far count.
    assert checkpoints == [10, 20]


def test_calibrate_loop_skips_checkpoint_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`checkpoint=None` (default) → no callback ever invoked."""
    from tests.calibration import run as run_mod
    from tests.calibration.run import _calibrate_loop

    class _NoopSource:
        name = "metron"

        def __init__(self) -> None:
            # Per-instance to satisfy RUF012; matches the production
            # OnlineSource pattern.
            self.api_call_counts: dict[str, int] = {}

        def search(self, profile):
            return []

    monkeypatch.setattr(
        run_mod,
        "_score_one",
        lambda s, f: _outcome(source=s.name, correct=True),  # noqa: ARG005
    )
    monkeypatch.setattr(Path, "exists", lambda self: True)  # noqa: ARG005

    fixtures = [_Fixture(Path(f"/x{i}.cbz"), {"metron": i}, "full") for i in range(15)]
    # No checkpoint passed; no exception, no callback fires.
    outcomes = _calibrate_loop(
        fixtures,
        [_NoopSource()],  # type: ignore[list-item]
    )
    assert len(outcomes) == 15


def test_build_checkpoint_labeled_path(tmp_path: Path) -> None:
    """A `label` argument routes to the labeled path."""
    from tests.calibration.run import _build_checkpoint

    fp = tmp_path / "fixtures.json"
    outcomes_path = tmp_path / "fixtures.outcomes.json"
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=outcomes_path,
        label="exhaustive",
        was_filtered=False,
    )
    cp([_outcome(score=0.9)])
    labeled = tmp_path / "fixtures.outcomes.exhaustive.json"
    assert labeled.exists()
    # Canonical path was NOT touched.
    assert not outcomes_path.exists()


def test_build_checkpoint_filtered_uses_merge(tmp_path: Path) -> None:
    """A filtered run's checkpoint goes through the partial-merge path."""
    from tests.calibration.run import _build_checkpoint, _serialize_outcomes

    fp = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    # Seed the partial with an entry that should be preserved.
    _serialize_outcomes(
        [
            _Outcome(
                fixture=_Fixture(Path("/old.cbz"), {"comicvine": 1}, "full"),
                source_name="comicvine",
                top_score=0.0,
                top_issue_id=None,
                top_correct=False,
                n_candidates=0,
            )
        ],
        partial,
    )
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=tmp_path / "fixtures.outcomes.json",
        label=None,
        was_filtered=True,
    )
    cp([_outcome(source="metron", score=0.95, correct=True)])
    payload = json.loads(partial.read_text())
    # Old entry preserved (the merge), new entry added.
    files = {e["file"] for e in payload}
    assert "/old.cbz" in files
    assert "/x.cbz" in files


def test_build_checkpoint_canonical_path(tmp_path: Path) -> None:
    """Non-filtered, non-labeled runs write to canonical outcomes path."""
    from tests.calibration.run import _build_checkpoint

    fp = tmp_path / "fixtures.json"
    outcomes_path = tmp_path / "fixtures.outcomes.json"
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=outcomes_path,
        label=None,
        was_filtered=False,
    )
    cp([_outcome(score=0.9)])
    assert outcomes_path.exists()
