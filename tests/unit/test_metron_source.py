"""
MetronOnlineSource search-flow tests.

Exercises the documented two-step pattern:
``series_list({name})`` → ``issues_list({series=id, number, cover_year})``.
Mocks `_get_session` so we never hit the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from comicbox.config.settings import OnlineSettings, OnlineSourceCredentials
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
        sid = params.get("series")
        if sid is None:
            return []
        return list(self._issues_by_series.get(int(sid), []))


def _make_metron_source(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeMokkari
) -> MetronOnlineSource:
    creds = OnlineSourceCredentials(username="u", password="p")
    settings = OnlineSettings()
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
    series_ids = [call.get("series") for call in fake.issues_list_calls]
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
            if (params or {}).get("series") == 101:
                msg = "boom"
                raise RuntimeError(msg)
            return super().issues_list(params)

    fake = _FlakyMokkari(series=[s1, s2], issues_by_series=issues)
    src = _make_metron_source(monkeypatch, fake)
    profile = ComicProfile(series="X", issue="1", issue_int=1)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [5001]
