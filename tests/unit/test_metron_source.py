"""
MetronOnlineSource search-flow tests.

Exercises the single-call search: ``issues_list({series_name, number,
cover_year, series_volume})`` directly, with no separate series-discovery
step. Since mokkari 3.28.0 / Metron server commit 3b1e46b,
`BaseIssue.series.id` is populated on list results, so `Candidate.volume_id`
resolves straight from the search result too. Mocks `_get_session` so we
never hit the network.
"""

from __future__ import annotations

from typing import Any

import pytest
from typing_extensions import override

from comicbox.config.settings import (
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.metron_api.online_source import MetronOnlineSource


class _FakeBaseSeries:
    def __init__(self, sid: int, name: str) -> None:
        self.id = sid
        self.name = name


class _FakeBaseIssue:
    def __init__(
        self,
        iid: int,
        number: str,
        series_name: str,
        cover_year: int = 1952,
        series_id: int = 999,
    ) -> None:
        from datetime import date

        self.id = iid
        self.number = number
        self.cover_date = date(cover_year, 1, 1)
        self.image = f"https://example.com/issue/{iid}.jpg"
        self.resource_url = f"https://example.com/issue/{iid}"
        self.cover_hash = None
        # mokkari `BaseIssue.series` is `BasicSeries` — since mokkari 3.28.0
        # / Metron server commit 3b1e46b it carries a real `.id` alongside
        # `name`, not just a sparse name-only stub.
        self.series = _FakeBaseSeries(sid=series_id, name=series_name)


class _FakeMokkari:
    """
    Mock mokkari.Session that records the calls it receives.

    ``issues_by_key`` is keyed by whatever identifier a call actually
    sends — the ``series_name`` string for the by-name search path, or the
    ``series_id`` int for the `--series-id` fast path / volume-scoped
    lookup. There's no `series_list` method: production code no longer
    calls it.
    """

    def __init__(self, issues_by_key: dict[Any, list[_FakeBaseIssue]]) -> None:
        self._issues_by_key = issues_by_key
        self.issues_list_calls: list[dict[str, Any]] = []

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        key = params.get("series_name")
        if key is None:
            key = params.get("series_id")
        if key is None:
            return []
        return list(self._issues_by_key.get(key, []))


def _make_metron_source(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari
) -> MetronOnlineSource:
    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings()
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def test_search_returns_empty_with_no_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile without a series name skips the API entirely."""
    fake = _FakeMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(issue="7", issue_int=7, year=1952)
    assert src.search(profile) == []
    assert fake.issues_list_calls == []


def test_search_issues_list_uses_series_name_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search() calls issues_list(series_name=...) directly, no discovery step."""
    issues = {
        "GI Joe": [
            _FakeBaseIssue(iid=5001, number="7", series_name="G.I. Joe", series_id=100)
        ],
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_name"] == "GI Joe"
    assert call["number"] == "7"  # leading zeros stripped
    assert call["cover_year"] == 1952

    assert [c.issue_id for c in candidates] == [5001]
    # Series name on the candidate comes straight from BaseIssue.series.name.
    assert candidates[0].summary.series == "G.I. Joe"
    # volume_id comes straight from BaseIssue.series.id (mokkari 3.28.0+) —
    # no discovery step needed to resolve it.
    assert candidates[0].volume_id == 100


def test_search_primary_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hard failure on the year-exact call raises, not returns []."""

    class _FailingMokkari(_FakeMokkari):
        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            self.issues_list_calls.append(dict(params or {}))
            msg = "boom"
            raise ValueError(msg)

    fake = _FailingMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="X", issue="1", issue_int=1, year=2020)
    with pytest.raises(ValueError, match="boom"):
        src.search(profile)


def test_search_year_retry_attempt_failure_does_not_block_sibling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing Y-1 retry attempt doesn't block the Y+1 attempt from running."""

    class _FlakyYearMokkari(_FakeMokkari):
        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            params = dict(params or {})
            self.issues_list_calls.append(params)
            year = params.get("cover_year")
            if year == 2019:
                msg = "boom at 2019"
                raise ValueError(msg)
            if year == 2021:
                return [
                    _FakeBaseIssue(
                        iid=901,
                        number="1",
                        series_name="Foo",
                        cover_year=2021,
                        series_id=100,
                    )
                ]
            return []

    fake = _FlakyYearMokkari(issues_by_key={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [901]
    years_tried = [c.get("cover_year") for c in fake.issues_list_calls]
    assert years_tried == [2020, 2019, 2021]


def test_search_retries_per_call_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Per-call retry honors the server's retry_after and replays the call.

    Before this fix, a `RateLimitError` from mokkari was caught by the old
    per-series fan-out's `except Exception: continue` and silently dropped
    that series' issue data. With `@with_retry()` on
    `_issues_list_with_retry`, the retry decorator catches the error,
    sleeps the hinted duration, and replays the same call.
    """
    issues = {
        "A": [_FakeBaseIssue(iid=5001, number="1", series_name="A", series_id=100)],
    }

    # mokkari-shaped exception: the retry decorator keys on the type
    # name string "RateLimitError" and the `retry_after` attribute.
    class RateLimitError(Exception):
        def __init__(self, retry_after: float) -> None:
            super().__init__("Rate limit exceeded")
            self.retry_after = retry_after

    class _RateLimitedMokkari(_FakeMokkari):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._fail_count = 0

        @override
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            if self._fail_count < 1:
                # Record the failed attempt too so we can assert retry count.
                self.issues_list_calls.append(dict(params or {}))
                self._fail_count += 1
                raise RateLimitError(retry_after=0.001)
            return super().issues_list(params)

    fake = _RateLimitedMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="A", issue="1", issue_int=1)
    candidates = src.search(profile)
    # The retry succeeded — we got the issue (before the fix, the
    # rate-limit error was swallowed by `except Exception: continue`
    # and the candidate list was empty).
    assert [c.issue_id for c in candidates] == [5001]
    # Two issues_list calls happened: the rate-limited one + the replay.
    assert len(fake.issues_list_calls) == 2


# ---------------------------------------------------------- --series-id


def _make_metron_source_with_series_id(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari, series_id: int
) -> MetronOnlineSource:
    from comicbox.config.settings import OnlineLookupSettings

    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings(
        lookup=OnlineLookupSettings(series_ids={"metron": series_id})
    )
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def test_series_id_skips_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN goes straight to a single issues_list call."""
    issues = {
        200: [
            _FakeBaseIssue(iid=9001, number="7", series_name="Bypassed", series_id=200)
        ]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_id"] == 200
    assert call["number"] == "7"  # leading zeros stripped
    assert call["cover_year"] == 1952
    assert [c.issue_id for c in candidates] == [9001]


def test_series_id_works_without_profile_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --series-id is set, missing profile.series is fine."""
    issues = {
        300: [_FakeBaseIssue(iid=9002, number="1", series_name="Direct", series_id=300)]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=300)
    profile = ComicProfile(issue="1", issue_int=1)  # no series at all
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [9002]


def test_to_candidate_propagates_series_id_from_search_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """By-name search candidates carry volume_id straight from BaseIssue.series.id."""
    issues = {
        "Watchmen": [
            _FakeBaseIssue(
                iid=27650, number="5", series_name="Watchmen", series_id=10455
            )
        ],
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    [cand] = src.search(profile)
    assert cand.volume_id == 10455


def test_to_candidate_propagates_series_id_from_series_id_fastpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN candidates also carry the series id."""
    # `series_id=999` on the fake issue itself deliberately mismatches the
    # explicit `series_id=77` supplied to the fast path, so the assertion
    # below proves the explicit id wins over `BaseIssue.series.id`.
    issues = {
        77: [
            _FakeBaseIssue(iid=9001, number="7", series_name="Bypassed", series_id=999)
        ]
    }
    fake = _FakeMokkari(issues_by_key=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=77)
    profile = ComicProfile(series="X", issue="7", issue_int=7, year=1952)
    [cand] = src.search(profile)
    assert cand.volume_id == 77


# ---------------------------------------------------------- ±1 year retry


class _YearAwareMokkari(_FakeMokkari):
    """`issues_list` honors `cover_year` so we can exercise retry-on-miss."""

    def __init__(
        self,
        issues_by_name_and_year: dict[tuple[str, int], list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(issues_by_key={})
        self._issues_by_name_and_year = issues_by_name_and_year

    @override
    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        name = params.get("series_name")
        year = params.get("cover_year")
        if name is None or year is None:
            return []
        return list(self._issues_by_name_and_year.get((name, int(year)), []))


def test_year_retry_on_miss_finds_at_year_minus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact returns nothing → retry at Y-1 succeeds."""
    issues_by_year = {
        ("Foo", 2019): [
            _FakeBaseIssue(
                iid=900, number="1", series_name="Foo", cover_year=2019, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [900]
    # Three issues_list calls: the year-exact (2020), then Y-1 (2019)
    # which hit, then Y+1 (2021) which the implementation runs eagerly.
    years_tried = [c.get("cover_year") for c in fake.issues_list_calls]
    assert years_tried == [2020, 2019, 2021]


def test_year_retry_on_miss_finds_at_year_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact returns nothing → retry at Y+1 succeeds."""
    issues_by_year = {
        ("Foo", 2021): [
            _FakeBaseIssue(
                iid=901, number="1", series_name="Foo", cover_year=2021, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [901]


def test_year_exact_hit_does_not_trigger_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When year-exact returns candidates, no Y±1 calls are made."""
    issues_by_year = {
        ("Foo", 2020): [
            _FakeBaseIssue(
                iid=900, number="1", series_name="Foo", cover_year=2020, series_id=100
            )
        ],
    }
    fake = _YearAwareMokkari(issues_by_name_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [900]
    years_tried = [c.get("cover_year") for c in fake.issues_list_calls]
    assert years_tried == [2020]  # no retries


def test_no_year_means_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile without a year skips the year filter and the retry path."""
    fake = _YearAwareMokkari(issues_by_name_and_year={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1)  # no year
    candidates = src.search(profile)

    assert candidates == []
    # Exactly one issues_list call (the original) — no Y-1 / Y+1 because
    # there's no year to relax.
    assert len(fake.issues_list_calls) == 1
    assert "cover_year" not in fake.issues_list_calls[0]


# ---------------------------------------------------------- volume filter


class _VolumeAwareMokkari(_FakeMokkari):
    """
    Honor `series_name`/`series_id`, `series_volume`, and `cover_year` filters.

    Used to test both the volume soft-filter and the drop-volume retry,
    across both the by-name search path and the `--series-id` fast path.
    """

    def __init__(
        self,
        # Keyed by (series_name_or_id, cover_year, series_volume_or_None).
        # `dict[tuple, ...]` is intentionally loose so test fixtures don't
        # need matching annotations on every literal tuple.
        issues_by_match: dict[tuple, list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(issues_by_key={})
        self._issues_by_match = issues_by_match

    @override
    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        ident = params.get("series_name")
        if ident is None:
            ident = params.get("series_id")
        if ident is None:
            return []
        year = params.get("cover_year")
        vol = params.get("series_volume")
        key = (
            ident,
            int(year) if year is not None else None,
            int(vol) if vol is not None else None,
        )
        return list(self._issues_by_match.get(key, []))


def test_volume_filter_passed_to_metron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`profile.volume` is passed as `series_volume` on the first pass."""
    issues = {
        ("Spider-Man", 2020, 2): [
            _FakeBaseIssue(
                iid=400,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [400]
    # First (and only) call carried both filters.
    assert len(fake.issues_list_calls) == 1
    call = fake.issues_list_calls[0]
    assert call["series_volume"] == 2
    assert call["cover_year"] == 2020


def test_volume_filter_drop_retry_finds_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Drop-volume retry path.

    Wrong volume in the filename → year-cycle with volume returns 0 →
    retry without volume succeeds.
    """
    # Match exists at series_volume=None (i.e. unfiltered), NOT 2.
    issues = {
        ("Spider-Man", 2020, None): [
            _FakeBaseIssue(
                iid=500,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [500]
    # Call sequence: year-exact w/ volume (miss), Y-1 w/ volume (miss),
    # Y+1 w/ volume (miss), THEN drop-volume year-exact (hit).
    series_volumes = [c.get("series_volume") for c in fake.issues_list_calls]
    assert series_volumes[0] == 2  # first pass had volume
    # The drop-volume retry pass omits series_volume entirely.
    assert any(sv is None for sv in series_volumes)


def test_no_volume_in_profile_no_drop_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile without volume skips the drop-volume retry path entirely."""
    fake = _VolumeAwareMokkari(issues_by_match={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)  # no volume
    candidates = src.search(profile)

    assert candidates == []
    # No call ever included series_volume, and there was no second cycle.
    assert all("series_volume" not in c for c in fake.issues_list_calls)
    # Three calls (year-exact + ±1 retry); no fourth-and-beyond drop pass.
    assert len(fake.issues_list_calls) == 3


def test_volume_match_does_not_trigger_drop_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact + volume hits → no drop-volume retry needed."""
    issues = {
        ("Spider-Man", 2020, 2): [
            _FakeBaseIssue(
                iid=600,
                number="1",
                series_name="Spider-Man",
                cover_year=2020,
                series_id=100,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=2
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [600]
    # Only the first call ran — no year retry, no volume drop.
    assert len(fake.issues_list_calls) == 1


def test_series_id_path_omits_volume_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id trumps volume; the filter is skipped on that fast path."""
    issues = {
        (200, 2020, None): [
            _FakeBaseIssue(
                iid=700,
                number="1",
                series_name="Bypassed",
                cover_year=2020,
                series_id=200,
            )
        ],
    }
    fake = _VolumeAwareMokkari(issues_by_match=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=99
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [700]
    assert len(fake.issues_list_calls) == 1
    assert "series_volume" not in fake.issues_list_calls[0]


def test_get_session_memoizes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream client is built once per source lifetime, then reused."""
    creds = OnlineSourceCredentials(user="u", password="p")
    settings = OnlineSettings()
    src = MetronOnlineSource(creds, settings)
    builds = {"n": 0}

    def fake_build():
        builds["n"] += 1
        return object()

    monkeypatch.setattr(src, "_build_session", fake_build)
    first = src._get_session()
    second = src._get_session()
    assert first is second
    assert builds["n"] == 1
