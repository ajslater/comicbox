"""
MetronOnlineSource search-flow tests.

Exercises the documented two-step pattern:
``series_list({name})`` → ``issues_list({series=id, number, cover_year})``.
Mocks `_get_session` so we never hit the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from comicbox.config.settings import (
    APIBudget,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.online.profile import ComicProfile
from comicbox.online.sources.metron import MetronOnlineSource

if TYPE_CHECKING:
    import pytest


class _FakeBaseSeries:
    def __init__(self, sid: int, name: str) -> None:
        self.id = sid
        self.name = name
        self.display_name = name


class _FakeBaseIssue:
    def __init__(
        self,
        iid: int,
        number: str,
        series_name: str,
        cover_year: int = 1952,
    ) -> None:
        from datetime import date

        self.id = iid
        self.number = number
        self.cover_date = date(cover_year, 1, 1)
        self.image = f"https://example.com/issue/{iid}.jpg"
        self.resource_url = f"https://example.com/issue/{iid}"
        self.cover_hash = None
        # mokkari `BaseIssue.series` is a sparse `BaseSeries`-shaped object.
        self.series = _FakeBaseSeries(sid=999, name=series_name)


class _FakeMokkari:
    """Mock mokkari.Session that records the calls it receives."""

    def __init__(
        self,
        series: list[_FakeBaseSeries],
        issues_by_series: dict[int, list[_FakeBaseIssue]],
    ) -> None:
        self._series = series
        self._issues_by_series = issues_by_series
        self.series_list_calls: list[dict[str, Any]] = []
        self.issues_list_calls: list[dict[str, Any]] = []

    def series_list(self, params: dict | None = None) -> list[_FakeBaseSeries]:
        self.series_list_calls.append(dict(params or {}))
        return list(self._series)

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        sid = params.get("series_id")
        if sid is None:
            return []
        return list(self._issues_by_series.get(int(sid), []))


def _make_metron_source(
    monkeypatch: pytest.MonkeyPatch,
    fake: _FakeMokkari,
    *,
    api_budget: APIBudget = APIBudget.EXHAUSTIVE,
) -> MetronOnlineSource:
    """
    Build a Metron source for tests with the pre-filter OFF by default.

    Unit tests in this file use synthetic series names that don't share
    tokens with `profile.series` (e.g., 25 series named `S0`..`S24` vs
    profile.series=`X`). Under the production default `BALANCED` budget
    (pre-filter threshold 0.4) those tests would have every candidate
    series dropped by the pre-filter before the code under test ran.
    Using `EXHAUSTIVE` for the default keeps these tests focused on the
    behavior they're verifying (caps, retry, candidate plumbing) without
    tripping on pre-filter side-effects. Tests that exercise the
    pre-filter explicitly can override `api_budget=`.
    """
    creds = OnlineSourceCredentials(username="u", password="p")
    settings = OnlineSettings(api_budget=api_budget)
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def test_search_returns_empty_with_no_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile without a series name skips the API entirely."""
    fake = _FakeMokkari(series=[], issues_by_series={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(issue="7", issue_int=7, year=1952)
    assert src.search(profile) == []
    assert fake.series_list_calls == []
    assert fake.issues_list_calls == []


def test_search_calls_series_list_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 1: discover series via the documented `series_list({name})`."""
    fake = _FakeMokkari(series=[], issues_by_series={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="GI Joe", issue="7", issue_int=7, year=1952)
    src.search(profile)
    assert fake.series_list_calls == [{"name": "GI Joe"}]
    # No series found → no issue lookup.
    assert fake.issues_list_calls == []


def test_search_two_step_returns_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step 2: per-series `issues_list({series=id, number, cover_year})`."""
    s1 = _FakeBaseSeries(sid=100, name="G.I. Joe")
    s2 = _FakeBaseSeries(sid=101, name="GI Joe Vol. 2")
    issues = {
        100: [_FakeBaseIssue(iid=5001, number="7", series_name="G.I. Joe")],
        101: [_FakeBaseIssue(iid=5002, number="7", series_name="GI Joe Vol. 2")],
    }
    fake = _FakeMokkari(series=[s1, s2], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    assert len(candidates) == 2
    assert {c.issue_id for c in candidates} == {5001, 5002}

    # Both series got their own issue lookup.
    series_ids = [call.get("series_id") for call in fake.issues_list_calls]
    assert sorted(series_ids) == [100, 101]

    # Issue number flowed through stripped of leading zeros.
    assert all(call.get("number") == "7" for call in fake.issues_list_calls)
    # Cover year carried.
    assert all(call.get("cover_year") == 1952 for call in fake.issues_list_calls)

    # Series name on candidates is the canonical Metron name (from series_list),
    # not the user's punctuation-thin profile.series.
    assert {c.summary.series for c in candidates} == {"G.I. Joe", "GI Joe Vol. 2"}


def test_search_caps_series_per_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When series_list returns many matches, we cap the issue lookups."""
    cap = MetronOnlineSource._MAX_SERIES_PER_SEARCH
    series = [_FakeBaseSeries(sid=i, name=f"S{i}") for i in range(cap + 5)]
    fake = _FakeMokkari(series=series, issues_by_series={})
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="X", issue="1", issue_int=1)
    src.search(profile)
    assert len(fake.issues_list_calls) == cap


def test_search_continues_on_per_series_issue_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad series shouldn't tank the whole search."""
    s1 = _FakeBaseSeries(sid=100, name="OK")
    s2 = _FakeBaseSeries(sid=101, name="BAD")
    issues = {100: [_FakeBaseIssue(iid=5001, number="1", series_name="OK")]}

    class _FlakyMokkari(_FakeMokkari):
        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            self.issues_list_calls.append(dict(params or {}))
            if (params or {}).get("series_id") == 101:
                # Use a non-retriable exception (ValueError is in
                # `_NON_RETRIABLE`) so we exercise the `except / continue`
                # fallback directly — RuntimeError would be retried by
                # @with_retry and burn 31s of exponential backoff.
                msg = "bad params"
                raise ValueError(msg)
            return super().issues_list(params)

    fake = _FlakyMokkari(series=[s1, s2], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="X", issue="1", issue_int=1)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [5001]


def test_search_retries_per_call_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Per-call retry honors the server's retry_after and replays the call.

    Before this fix, a `RateLimitError` from mokkari was caught by the
    `_fetch_candidates_across_series` loop's `except Exception: continue`
    and silently dropped that series' issue data. With `@with_retry()`
    on `_issues_list_with_retry`, the retry decorator catches the error,
    sleeps the hinted duration, and replays the same call.
    """
    s1 = _FakeBaseSeries(sid=100, name="A")
    issues = {100: [_FakeBaseIssue(iid=5001, number="1", series_name="A")]}

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

        def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
            if self._fail_count < 1:
                # Record the failed attempt too so we can assert retry count.
                self.issues_list_calls.append(dict(params or {}))
                self._fail_count += 1
                raise RateLimitError(retry_after=0.001)
            return super().issues_list(params)

    fake = _RateLimitedMokkari(series=[s1], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="A", issue="1", issue_int=1)
    candidates = src.search(profile)
    # The retry succeeded — we got the issue (before the fix, the
    # rate-limit error was swallowed by `except Exception: continue`
    # and the candidate list was empty).
    assert [c.issue_id for c in candidates] == [5001]
    # Two issues_list calls happened: the rate-limited one + the replay.
    assert len(fake.issues_list_calls) == 2


def test_search_retries_series_list_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `series_list` is now also retry-wrapped.

    Pre-fix: a `RateLimitError` from `series_list` propagated up
    through `except Exception: ... raise`, dropping the whole
    fixture's candidate set. The 2026-05-15-stress-100 run counted 86
    such cases in 100 fixtures. With `_series_list_with_retry`, the
    retry decorator catches the error, sleeps the hinted duration,
    and replays the call.
    """
    s1 = _FakeBaseSeries(sid=100, name="A")
    issues = {100: [_FakeBaseIssue(iid=5001, number="1", series_name="A")]}

    class RateLimitError(Exception):
        def __init__(self, retry_after: float) -> None:
            super().__init__("Rate limit exceeded")
            self.retry_after = retry_after

    class _SeriesRateLimitedMokkari(_FakeMokkari):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._fail_count = 0

        def series_list(self, params: dict | None = None) -> list[_FakeBaseSeries]:
            if self._fail_count < 1:
                self.series_list_calls.append(dict(params or {}))
                self._fail_count += 1
                raise RateLimitError(retry_after=0.001)
            return super().series_list(params)

    fake = _SeriesRateLimitedMokkari(series=[s1], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="A", issue="1", issue_int=1)
    candidates = src.search(profile)
    # The retry succeeded — we got the issue. Pre-fix, the rate-limit
    # error from series_list would have aborted the whole search.
    assert [c.issue_id for c in candidates] == [5001]
    # Two series_list calls happened: the rate-limited one + the replay.
    assert len(fake.series_list_calls) == 2


# ---------------------------------------------------------- --series-id


def _make_metron_source_with_series_id(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari, series_id: int
) -> MetronOnlineSource:
    creds = OnlineSourceCredentials(username="u", password="p")
    settings = OnlineSettings(explicit_series_ids={"metron": series_id})
    src = MetronOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake)
    return src


def test_series_id_skips_series_list_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN goes straight to issues_list, no series_list."""
    issues = {200: [_FakeBaseIssue(iid=9001, number="7", series_name="Bypassed")]}
    fake = _FakeMokkari(series=[], issues_by_series=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    # Step 1 (series_list) was skipped entirely.
    assert fake.series_list_calls == []
    # Step 2 ran exactly once with the explicit series id.
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
    issues = {300: [_FakeBaseIssue(iid=9002, number="1", series_name="Direct")]}
    fake = _FakeMokkari(series=[], issues_by_series=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=300)
    profile = ComicProfile(issue="1", issue_int=1)  # no series at all
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [9002]
    assert fake.series_list_calls == []


def test_to_candidate_propagates_series_id_from_two_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidates carry the parent series.id (from the discovery step)."""
    s = _FakeBaseSeries(sid=10455, name="Watchmen")
    issues = {10455: [_FakeBaseIssue(iid=27650, number="5", series_name="Watchmen")]}
    fake = _FakeMokkari(series=[s], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    [cand] = src.search(profile)
    # Comes from the series discovery step, not from BaseIssue.series.id
    # (which is the sparse fake-default 999) — explicit threading wins.
    assert cand.volume_id == 10455


def test_to_candidate_propagates_series_id_from_series_id_fastpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id metron:NNN candidates also carry the series id."""
    issues = {77: [_FakeBaseIssue(iid=9001, number="7", series_name="Bypassed")]}
    fake = _FakeMokkari(series=[], issues_by_series=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=77)
    profile = ComicProfile(series="X", issue="7", issue_int=7, year=1952)
    [cand] = src.search(profile)
    assert cand.volume_id == 77


# ---------------------------------------------------------- ±1 year retry


class _YearAwareMokkari(_FakeMokkari):
    """`issues_list` honors `cover_year` so we can exercise retry-on-miss."""

    def __init__(
        self,
        series: list[_FakeBaseSeries],
        issues_by_series_and_year: dict[tuple[int, int], list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(series=series, issues_by_series={})
        self._issues_by_series_and_year = issues_by_series_and_year

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        sid = params.get("series_id")
        year = params.get("cover_year")
        if sid is None or year is None:
            return []
        return list(self._issues_by_series_and_year.get((int(sid), int(year)), []))


def test_year_retry_on_miss_finds_at_year_minus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Year-exact returns nothing → retry at Y-1 succeeds."""
    s = _FakeBaseSeries(sid=100, name="Foo")
    issues_by_year = {
        (100, 2019): [
            _FakeBaseIssue(iid=900, number="1", series_name="Foo", cover_year=2019)
        ],
    }
    fake = _YearAwareMokkari(series=[s], issues_by_series_and_year=issues_by_year)
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
    s = _FakeBaseSeries(sid=100, name="Foo")
    issues_by_year = {
        (100, 2021): [
            _FakeBaseIssue(iid=901, number="1", series_name="Foo", cover_year=2021)
        ],
    }
    fake = _YearAwareMokkari(series=[s], issues_by_series_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [901]


def test_year_exact_hit_does_not_trigger_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When year-exact returns candidates, no Y±1 calls are made."""
    s = _FakeBaseSeries(sid=100, name="Foo")
    issues_by_year = {
        (100, 2020): [
            _FakeBaseIssue(iid=900, number="1", series_name="Foo", cover_year=2020)
        ],
    }
    fake = _YearAwareMokkari(series=[s], issues_by_series_and_year=issues_by_year)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [900]
    years_tried = [c.get("cover_year") for c in fake.issues_list_calls]
    assert years_tried == [2020]  # no retries


def test_no_year_means_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Profile without a year skips the year filter and the retry path."""
    s = _FakeBaseSeries(sid=100, name="Foo")
    fake = _YearAwareMokkari(series=[s], issues_by_series_and_year={})
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
    `issues_list` honors `series_volume` and `cover_year` filters.

    Used to test both the volume soft-filter and the drop-volume retry.
    """

    def __init__(
        self,
        series: list[_FakeBaseSeries],
        # Keyed by (series_id, cover_year, series_volume_or_None).
        # `dict[tuple, ...]` is intentionally loose so test fixtures don't
        # need matching `int | None` annotations on every literal tuple.
        issues_by_match: dict[tuple, list[_FakeBaseIssue]],
    ) -> None:
        super().__init__(series=series, issues_by_series={})
        self._issues_by_match = issues_by_match

    def issues_list(self, params: dict | None = None) -> list[_FakeBaseIssue]:
        params = dict(params or {})
        self.issues_list_calls.append(params)
        sid = params.get("series_id")
        if sid is None:
            return []
        year = params.get("cover_year")
        vol = params.get("series_volume")
        key = (
            int(sid),
            int(year) if year is not None else None,
            int(vol) if vol is not None else None,
        )
        return list(self._issues_by_match.get(key, []))


def test_volume_filter_passed_to_metron(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`profile.volume` is passed as `series_volume` on the first pass."""
    s = _FakeBaseSeries(sid=100, name="Spider-Man")
    issues = {
        (100, 2020, 2): [
            _FakeBaseIssue(
                iid=400, number="1", series_name="Spider-Man", cover_year=2020
            )
        ],
    }
    fake = _VolumeAwareMokkari(series=[s], issues_by_match=issues)
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
    s = _FakeBaseSeries(sid=100, name="Spider-Man")
    # Match exists at series_volume=1, NOT 2.
    issues = {
        (100, 2020, None): [
            _FakeBaseIssue(
                iid=500, number="1", series_name="Spider-Man", cover_year=2020
            )
        ],
    }
    fake = _VolumeAwareMokkari(series=[s], issues_by_match=issues)
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
    s = _FakeBaseSeries(sid=100, name="Foo")
    fake = _VolumeAwareMokkari(series=[s], issues_by_match={})
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
    s = _FakeBaseSeries(sid=100, name="Spider-Man")
    issues = {
        (100, 2020, 2): [
            _FakeBaseIssue(
                iid=600, number="1", series_name="Spider-Man", cover_year=2020
            )
        ],
    }
    fake = _VolumeAwareMokkari(series=[s], issues_by_match=issues)
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
            _FakeBaseIssue(iid=700, number="1", series_name="Bypassed", cover_year=2020)
        ],
    }
    fake = _VolumeAwareMokkari(series=[], issues_by_match=issues)
    src = _make_metron_source_with_series_id(monkeypatch, fake, series_id=200)
    profile = ComicProfile(
        series="Spider-Man", issue="1", issue_int=1, year=2020, volume=99
    )
    candidates = src.search(profile)

    assert [c.issue_id for c in candidates] == [700]
    assert len(fake.issues_list_calls) == 1
    assert "series_volume" not in fake.issues_list_calls[0]
