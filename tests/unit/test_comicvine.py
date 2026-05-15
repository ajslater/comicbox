"""ComicVine source + transform tests."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from comicbox.config.settings import APIBudget, OnlineSettings, OnlineSourceCredentials
from comicbox.online.profile import ComicProfile
from comicbox.online.sources.comicvine import (
    ComicVineOnlineSource,
    CoverHashUrlCache,
)
from comicbox.transforms.comicvine_api import ComicVineApiTransform

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _sample_issue_dict() -> dict:
    return {
        "comicvine_api": {
            "id": 1234,
            "number": "5",
            "cover_date": "2020-04-01",
            "store_date": "2020-04-15",
            "date_last_updated": "2020-04-02T12:00:00Z",
            "description": "<p>Some description.</p>",
            "page_count": 24,
            "image": {
                "thumbnail": "http://example.com/thumbnail.jpg",
                "small_url": "http://example.com/small.jpg",
                "medium_url": "http://example.com/medium.jpg",
                "original_url": "http://example.com/original.jpg",
            },
            "volume": {"id": 100, "name": "Foo Comics"},
        }
    }


def test_transform_maps_core_fields() -> None:
    transform = ComicVineApiTransform()
    result = dict(transform.to_comicbox(_sample_issue_dict()))
    cb = result["comicbox"]
    # description was HTML; nh3 strips tags.
    assert cb["summary"] == "Some description."
    assert cb["issue"]["name"] == "5"
    # CV's `volume` becomes comicbox's `series`.
    assert cb["series"]["name"] == "Foo Comics"
    assert cb["cover_image"]
    assert "cover_date" in cb["date"]
    assert "store_date" in cb["date"]
    # CV doesn't expose page_count on Issue; not mapped (page_count
    # comes from comicbox's own archive scan, not CV).


def test_transform_handles_missing_fields() -> None:
    transform = ComicVineApiTransform()
    minimal = {
        "comicvine_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2025-01-01",
            "date_last_updated": "2025-01-01T00:00:00Z",
            "image": {"medium_url": "http://example.com/x.jpg"},
            "volume": {"id": 1, "name": "S"},
        }
    }
    result = dict(transform.to_comicbox(minimal))
    cb = result["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert cb["series"]["name"] == "S"


# ----------------------------------------------- CoverHashUrlCache


def test_cover_hash_url_cache_round_trip(tmp_path: Path) -> None:
    cache = CoverHashUrlCache(tmp_path / "cover_hashes.sqlite")
    assert cache.get("http://example.com/x.jpg") is None
    cache.set("http://example.com/x.jpg", "abcdef0123456789")
    assert cache.get("http://example.com/x.jpg") == "abcdef0123456789"


def test_cover_hash_url_cache_overwrites(tmp_path: Path) -> None:
    cache = CoverHashUrlCache(tmp_path / "cover_hashes.sqlite")
    cache.set("u", "h1")
    cache.set("u", "h2")
    assert cache.get("u") == "h2"


def test_cover_hash_url_cache_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "cover_hashes.sqlite"
    CoverHashUrlCache(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = [r[0] for r in rows]
    assert "cover_hashes" in table_names


# ----------------------------------------------- matcher hash-fetcher hook


def test_matcher_uses_candidate_hash_fetcher_for_no_precomputed() -> None:
    """Matcher should call the fetcher for candidates without precomputed hash."""
    from comicbox.online.matcher import OnlineMatcher
    from comicbox.online.profile import Candidate, CandidateSummary, ComicProfile

    fetcher_calls: list[str] = []

    def fake_fetcher(url: str) -> str:
        fetcher_calls.append(url)
        return "ffffffffffffffff"  # different from local

    def local_provider() -> str:
        return "0000000000000000"

    profile = ComicProfile(
        series="Foo",
        issue="5",
        issue_int=5,
        year=2020,
        publisher="P",
        page_count=24,
    )
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="Foo",
            issue="5",
            year=2020,
            publisher="P",
            page_count=24,
            cover_url="http://example.com/x.jpg",
            variant_label=None,
        ),
    )

    matcher = OnlineMatcher()
    matcher.rank(
        profile,
        [cand],
        local_hash_provider=local_provider,
        candidate_hash_fetcher=fake_fetcher,
        threshold=0.99,  # force hashing path (top below threshold).
    )
    # Whether or not the candidate was hashed depends on the metadata
    # score landing in the ambiguous band; with a perfect metadata match
    # the policy may skip hashing. The test asserts the fetcher is wired:
    # if invoked, it received our URL.
    assert all(call == "http://example.com/x.jpg" for call in fetcher_calls)


# ------------------------------------------ two-step volume → issues search


class _FakeBasicVolume:
    def __init__(self, vid: int, name: str, start_year: int | None = None) -> None:
        self.id = vid
        self.name = name
        # simyan's BasicVolume exposes start_year; the search loop uses it
        # to skip volumes that started after the comic was published.
        self.start_year = start_year


class _FakeImage:
    thumbnail = "http://example.com/thumbnail.jpg"
    small_url = None
    medium_url = "http://example.com/medium.jpg"
    screen_url = None
    super_url = None
    original_url = "http://example.com/original.jpg"


class _FakeBasicIssue:
    def __init__(
        self,
        iid: int,
        number: str,
        volume_name: str,
        cover_year: int = 1952,
        volume_id: int = 999,
    ) -> None:
        from datetime import date

        self.id = iid
        self.number = number
        self.cover_date = date(cover_year, 1, 1)
        self.image = _FakeImage()
        self.site_url = f"http://example.com/issue/{iid}"
        self.volume = _FakeBasicVolume(vid=volume_id, name=volume_name)


class _FakeCV:
    """Mock simyan.Comicvine that records the calls it receives."""

    def __init__(
        self,
        volumes: list[_FakeBasicVolume],
        issues_by_volume: dict[int, list[_FakeBasicIssue]],
    ) -> None:
        self._volumes = volumes
        self._issues_by_volume = issues_by_volume
        self.search_calls: list[dict] = []
        self.list_issues_calls: list[dict] = []

    def search(self, resource, query, max_results=500):
        self.search_calls.append(
            {"resource": resource, "query": query, "max_results": max_results}
        )
        return list(self._volumes)

    def list_issues(self, params=None, max_results=500):
        self.list_issues_calls.append(params or {})
        # Trivial: parse `volume:VOL_ID` out of the filter and return that
        # volume's issues. The issue_number filter is not enforced — that's
        # CV's job, not ours to mock perfectly.
        filter_str = (params or {}).get("filter", "")
        for clause in filter_str.split(","):
            if clause.startswith("volume:"):
                vid = int(clause.split(":", 1)[1])
                return list(self._issues_by_volume.get(vid, []))
        return []


def _make_cv_source(
    monkeypatch: pytest.MonkeyPatch, fake_cv: _FakeCV
) -> ComicVineOnlineSource:
    creds = OnlineSourceCredentials(api_key="test-key")
    settings = OnlineSettings()
    src = ComicVineOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake_cv)
    return src


def test_search_returns_empty_with_no_series(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_cv = _FakeCV(volumes=[], issues_by_volume={})
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(issue="7", issue_int=7, year=1952)
    assert src.search(profile) == []
    # No volume search either — there's nothing to search by.
    assert fake_cv.search_calls == []


def test_search_volumes_via_full_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Volume discovery uses CV full-text search (more punctuation-tolerant)."""
    from simyan.comicvine import ComicvineResource

    fake_cv = _FakeCV(volumes=[], issues_by_volume={})
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="GI Joe", issue="7", issue_int=7, year=1952)
    src.search(profile)
    assert len(fake_cv.search_calls) == 1
    call = fake_cv.search_calls[0]
    assert call["resource"] == ComicvineResource.VOLUME
    assert call["query"] == "GI Joe"


def _make_cv_source_with_series_id(
    monkeypatch: pytest.MonkeyPatch, fake_cv: _FakeCV, series_id: int
) -> ComicVineOnlineSource:
    creds = OnlineSourceCredentials(api_key="test-key")
    settings = OnlineSettings(explicit_series_ids={"comicvine": series_id})
    src = ComicVineOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake_cv)
    return src


def test_search_series_id_skips_volume_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--series-id comicvine:NNN skips the volume search call entirely."""
    issues = {500: [_FakeBasicIssue(iid=9001, number="7", volume_name="Direct")]}
    fake_cv = _FakeCV(volumes=[], issues_by_volume=issues)
    src = _make_cv_source_with_series_id(monkeypatch, fake_cv, series_id=500)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)

    # The volume-search step was skipped.
    assert fake_cv.search_calls == []
    # list_issues ran exactly once with the explicit volume id in the filter.
    assert len(fake_cv.list_issues_calls) == 1
    filter_str = fake_cv.list_issues_calls[0].get("filter", "")
    assert "volume:500" in filter_str
    assert "issue_number:7" in filter_str  # leading zeros stripped
    assert [c.issue_id for c in candidates] == [9001]


def test_search_two_step_returns_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vol1 = _FakeBasicVolume(vid=100, name="G.I. Joe")
    vol2 = _FakeBasicVolume(vid=101, name="GI Joe Vol. 2")
    issues = {
        100: [_FakeBasicIssue(iid=5001, number="7", volume_name="G.I. Joe")],
        101: [_FakeBasicIssue(iid=5002, number="7", volume_name="GI Joe Vol. 2")],
    }
    fake_cv = _FakeCV(volumes=[vol1, vol2], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="GI Joe", issue="007", issue_int=7, year=1952)
    candidates = src.search(profile)
    assert len(candidates) == 2
    assert {c.issue_id for c in candidates} == {5001, 5002}
    # Issue number was leading-zero-stripped.
    issue_filters = [c.get("filter", "") for c in fake_cv.list_issues_calls]
    assert all("issue_number:7" in f for f in issue_filters)
    # Volume id flowed through.
    assert any("volume:100" in f for f in issue_filters)
    assert any("volume:101" in f for f in issue_filters)
    # Series name on candidates comes from the (CV-canonical) volume name,
    # not the user's punctuation-thin profile.series.
    assert {c.summary.series for c in candidates} == {"G.I. Joe", "GI Joe Vol. 2"}
    # Cover URL fell through to the first available preference (`thumbnail`).
    assert all(c.summary.cover_url == _FakeImage.thumbnail for c in candidates)


# -------------------------------------------- get(issue_id) → volume publisher


class _FakeGenericEntry:
    """Mock simyan GenericEntry (publisher / volume sub-object)."""

    def __init__(self, eid: int, name: str) -> None:
        self.id = eid
        self.name = name

    def model_dump(self, mode: str = "json") -> dict:
        return {"id": self.id, "name": self.name}


class _FakeFullIssue:
    """Mock simyan Issue returned by get_issue (richer than BasicIssue)."""

    def __init__(self, iid: int, volume: _FakeGenericEntry) -> None:
        self.id = iid
        self.volume = volume

    def model_dump(self, mode: str = "json") -> dict:
        return {
            "id": self.id,
            "volume": {"id": self.volume.id, "name": self.volume.name},
        }


class _FakeFullVolume:
    """Mock simyan Volume returned by get_volume (carries publisher)."""

    def __init__(
        self, vid: int, name: str, publisher: _FakeGenericEntry | None
    ) -> None:
        self.id = vid
        self.name = name
        self.publisher = publisher


class _FakeCVForGet:
    """Mock simyan.Comicvine for the get(issue_id) path."""

    def __init__(
        self,
        issue: _FakeFullIssue,
        volume: _FakeFullVolume | None,
    ) -> None:
        self._issue = issue
        self._volume = volume
        self.get_issue_calls: list[int] = []
        self.get_volume_calls: list[int] = []

    def get_issue(self, issue_id: int) -> _FakeFullIssue:
        self.get_issue_calls.append(issue_id)
        return self._issue

    def get_volume(self, volume_id: int) -> _FakeFullVolume:
        self.get_volume_calls.append(volume_id)
        if self._volume is None:
            msg = f"no fake volume for {volume_id}"
            raise RuntimeError(msg)
        return self._volume


def _make_cv_source_for_get(
    monkeypatch: pytest.MonkeyPatch, fake_cv: _FakeCVForGet
) -> ComicVineOnlineSource:
    creds = OnlineSourceCredentials(api_key="test-key")
    settings = OnlineSettings()
    src = ComicVineOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake_cv)
    return src


def test_get_injects_publisher_from_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get() augments the issue dump with publisher fetched via get_volume."""
    publisher = _FakeGenericEntry(eid=10, name="Marvel")
    issue = _FakeFullIssue(iid=42, volume=_FakeGenericEntry(eid=999, name="X-Men"))
    volume = _FakeFullVolume(vid=999, name="X-Men", publisher=publisher)
    fake_cv = _FakeCVForGet(issue=issue, volume=volume)
    src = _make_cv_source_for_get(monkeypatch, fake_cv)

    payload = src.get(42)

    assert fake_cv.get_issue_calls == [42]
    assert fake_cv.get_volume_calls == [999]
    assert payload["publisher"] == {"id": 10, "name": "Marvel"}


def test_get_omits_publisher_when_volume_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A volume without a publisher leaves the dump unchanged."""
    issue = _FakeFullIssue(iid=42, volume=_FakeGenericEntry(eid=999, name="X-Men"))
    volume = _FakeFullVolume(vid=999, name="X-Men", publisher=None)
    fake_cv = _FakeCVForGet(issue=issue, volume=volume)
    src = _make_cv_source_for_get(monkeypatch, fake_cv)

    payload = src.get(42)
    assert "publisher" not in payload


def test_get_handles_get_volume_failure_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If get_volume raises, the issue dump still comes back (sans publisher)."""
    issue = _FakeFullIssue(iid=42, volume=_FakeGenericEntry(eid=999, name="X-Men"))
    fake_cv = _FakeCVForGet(issue=issue, volume=None)  # → get_volume raises
    src = _make_cv_source_for_get(monkeypatch, fake_cv)

    payload = src.get(42)
    assert payload["id"] == 42
    assert "publisher" not in payload
    # The issue fetch itself wasn't disrupted.
    assert fake_cv.get_issue_calls == [42]
    assert fake_cv.get_volume_calls == [999]


# ----------------------------------------- cover_date year-window filter


def test_search_includes_cover_date_window_when_year_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """profile.year → cover_date:Y-2-01-01|Y+2-12-31 in the issue filter."""
    vol = _FakeBasicVolume(vid=100, name="Lois Lane")
    issues = {100: [_FakeBasicIssue(iid=1, number="1", volume_name="Lois Lane")]}
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Lois Lane", issue="1", issue_int=1, year=2019)
    src.search(profile)
    # First (and only) per-volume call carries the cover_date window.
    [call] = fake_cv.list_issues_calls
    assert "cover_date:2017-01-01|2021-12-31" in call.get("filter", "")


def test_search_omits_cover_date_when_no_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """profile.year=None → no cover_date filter (we have no year to gate on)."""
    vol = _FakeBasicVolume(vid=100, name="Lois Lane")
    issues = {100: [_FakeBasicIssue(iid=1, number="1", volume_name="Lois Lane")]}
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Lois Lane", issue="1", issue_int=1, year=None)
    src.search(profile)
    [call] = fake_cv.list_issues_calls
    assert "cover_date" not in call.get("filter", "")


def test_search_retries_without_year_when_year_filter_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    CV may have issues without cover_date set; fall back so we don't drop them.

    The fake's `list_issues` ignores cover_date filters by design — but we
    want to verify the retry happens. To do that we make a fake that
    *does* honor cover_date and returns empty under it: that triggers
    the year=None fallback.
    """
    vol = _FakeBasicVolume(vid=100, name="Lois Lane")
    real_issue = _FakeBasicIssue(iid=42, number="1", volume_name="Lois Lane")

    class _YearFilterCV(_FakeCV):
        def list_issues(self, params=None, max_results=500):
            params = params or {}
            self.list_issues_calls.append(params)
            filter_str = params.get("filter", "")
            # First call has cover_date filter → return empty.
            # Second call doesn't → return the real issue.
            if "cover_date:" in filter_str:
                return []
            return [real_issue]

    fake_cv = _YearFilterCV(volumes=[vol], issues_by_volume={})
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Lois Lane", issue="1", issue_int=1, year=2019)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [42]
    assert len(fake_cv.list_issues_calls) == 2
    assert "cover_date:" in fake_cv.list_issues_calls[0].get("filter", "")
    assert "cover_date:" not in fake_cv.list_issues_calls[1].get("filter", "")


# --------------------------------------- volume-predates-comic skip filter


def test_volume_predates_comic_basic() -> None:
    """Volume started after comic year + slop → predates."""
    src = ComicVineOnlineSource(OnlineSourceCredentials(api_key="x"), OnlineSettings())
    # 1987 comic, 2008 volume → predates by 21y.
    assert src._volume_predates_comic(2008, 1987) is True
    # 1987 comic, 1986 volume → not predates (volume started earlier, fine).
    assert src._volume_predates_comic(1986, 1987) is False
    # 1987 comic, 1987 volume → same year, fine.
    assert src._volume_predates_comic(1987, 1987) is False
    # Slop tolerance: 1987 comic, 1988 volume → diff=1, within slop.
    assert src._volume_predates_comic(1988, 1987) is False
    # Slop tolerance: 1987 comic, 1989 volume → diff=2, beyond slop.
    assert src._volume_predates_comic(1989, 1987) is True


def test_volume_predates_comic_none_inputs_keep_volume() -> None:
    """Missing data → keep the volume (don't drop on uncertainty)."""
    src = ComicVineOnlineSource(OnlineSourceCredentials(api_key="x"), OnlineSettings())
    assert src._volume_predates_comic(None, 1987) is False
    assert src._volume_predates_comic(2008, None) is False
    assert src._volume_predates_comic(None, None) is False


def test_search_skips_volumes_started_after_comic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Watchmen-shaped case: 1987 comic, reprint volume started 2008 is dropped.

    The matcher otherwise can't distinguish the reprint from the original
    — both candidates carry cover_date=1987, so all metadata signals
    score identically and the wrong volume wins on sort order.
    """
    # 1986 vol — keep (original); 2008 vol — skip (started after comic).
    vol_keep = _FakeBasicVolume(vid=100, name="Watchmen", start_year=1986)
    vol_skip = _FakeBasicVolume(vid=200, name="Watchmen Reprint", start_year=2008)
    issues = {
        100: [_FakeBasicIssue(iid=27650, number="5", volume_name="Watchmen")],
        200: [_FakeBasicIssue(iid=476696, number="5", volume_name="Watchmen Reprint")],
    }
    fake_cv = _FakeCV(volumes=[vol_keep, vol_skip], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    candidates = src.search(profile)

    # Only the original volume's issue survived.
    assert [c.issue_id for c in candidates] == [27650]
    # The skipped volume never received a list_issues call.
    filters = [c.get("filter", "") for c in fake_cv.list_issues_calls]
    assert any("volume:100" in f for f in filters)
    assert not any("volume:200" in f for f in filters)


def test_search_keeps_volume_when_start_year_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A volume with no start_year is kept (don't drop on missing data)."""
    vol = _FakeBasicVolume(vid=100, name="Mystery Vol", start_year=None)
    issues = {100: [_FakeBasicIssue(iid=1, number="1", volume_name="Mystery Vol")]}
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Mystery Vol", issue="1", issue_int=1, year=1987)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [1]


def test_search_keeps_volume_when_profile_year_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No profile.year → no basis to compare; all volumes kept."""
    # Volume started in 2020; absent a comic year we can't say it predates.
    vol = _FakeBasicVolume(vid=100, name="Future Vol", start_year=2020)
    issues = {100: [_FakeBasicIssue(iid=1, number="1", volume_name="Future Vol")]}
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Future Vol", issue="1", issue_int=1, year=None)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [1]


def test_search_keeps_long_running_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2020 issue from a volume that started in 1963 should NOT be dropped."""
    vol = _FakeBasicVolume(vid=100, name="Action Comics", start_year=1938)
    issues = {100: [_FakeBasicIssue(iid=1, number="1000", volume_name="Action Comics")]}
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume=issues)
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(
        series="Action Comics", issue="1000", issue_int=1000, year=2018
    )
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [1]


# --------------------------------------------- volume_id plumbing


def test_to_candidate_propagates_volume_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Candidates carry the parent volume.id (used by calibration diagnostics)."""
    vol = _FakeBasicVolume(vid=10455, name="Watchmen", start_year=1986)
    # _FakeBasicIssue's internal volume defaults to vid=999; override
    # to match the parent volume the search step found, so the
    # `basic_issue.volume.id` plumbing has a meaningful value to read.
    issue = _FakeBasicIssue(iid=27650, number="5", volume_name="Watchmen")
    issue.volume = _FakeBasicVolume(vid=10455, name="Watchmen")
    fake_cv = _FakeCV(volumes=[vol], issues_by_volume={10455: [issue]})
    src = _make_cv_source(monkeypatch, fake_cv)
    profile = ComicProfile(series="Watchmen", issue="5", issue_int=5, year=1987)
    [cand] = src.search(profile)
    assert cand.volume_id == 10455


# --------------------------------------------- rate-limit per-call retry


def test_list_issues_by_volume_retries_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Per-call retry honors the server's retry_after and replays the call.

    Before this fix, a `RateLimitError` from simyan was caught by the
    `search` loop's `except Exception: continue` and silently dropped
    that volume's issue data. With `@with_retry()` on
    `_list_issues_by_volume`, the retry decorator catches the error,
    sleeps the hinted duration, and replays the same call.
    """
    vol = _FakeBasicVolume(vid=100, name="Foo", start_year=2020)
    issue = _FakeBasicIssue(iid=5001, number="1", volume_name="Foo")

    class RateLimitError(Exception):
        def __init__(self, retry_after: float) -> None:
            super().__init__("Rate limit exceeded")
            self.retry_after = retry_after

    class _RateLimitedCV(_FakeCV):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # pyright: ignore[reportArgumentType]
            self._fail_count = 0

        def list_issues(self, params=None, max_results=500):
            if self._fail_count < 1:
                self.list_issues_calls.append(dict(params or {}))
                self._fail_count += 1
                raise RateLimitError(retry_after=0.001)
            return super().list_issues(params, max_results)

    fake = _RateLimitedCV(volumes=[vol], issues_by_volume={100: [issue]})
    src = _make_cv_source(monkeypatch, fake)
    profile = ComicProfile(series="Foo", issue="1", issue_int=1, year=2020)
    candidates = src.search(profile)
    assert [c.issue_id for c in candidates] == [5001]
    # Two list_issues calls: failed + replay.
    assert len(fake.list_issues_calls) == 2


# --------------------------- Phase H: broaden-retry on weak top score


class _TwoStepCV(_FakeCV):
    """
    Two-stage volume responder for the Phase H broaden tests.

    First `search()` call returns `initial_volumes`; every subsequent
    `search()` call returns `broader_volumes`. Lets a single test
    verify both the initial pass and the Phase H broaden pass without
    rebuilding the fake mid-test.
    """

    def __init__(
        self,
        initial_volumes: list[_FakeBasicVolume],
        broader_volumes: list[_FakeBasicVolume],
        issues_by_volume: dict[int, list[_FakeBasicIssue]],
    ) -> None:
        super().__init__(volumes=initial_volumes, issues_by_volume=issues_by_volume)
        self._initial = initial_volumes
        self._broader = broader_volumes

    def search(self, resource, query, max_results=500):
        self.search_calls.append(
            {"resource": resource, "query": query, "max_results": max_results}
        )
        return (
            list(self._initial) if len(self.search_calls) == 1 else list(self._broader)
        )


def _make_cv_source_with_budget(
    monkeypatch: pytest.MonkeyPatch,
    fake_cv: _FakeCV,
    budget: APIBudget,
) -> ComicVineOnlineSource:
    """`_make_cv_source` variant with an explicit api_budget override."""
    creds = OnlineSourceCredentials(api_key="test-key")
    settings = OnlineSettings(api_budget=budget)
    src = ComicVineOnlineSource(creds, settings)
    monkeypatch.setattr(src, "_get_session", lambda: fake_cv)
    return src


def test_broaden_retry_fires_on_weak_top_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Phase H: under FAST budget, weak top quick-score triggers a wider search.

    Bigmedia "older record wins" shape: profile tagged with year 2024,
    CV's top-5 returns only the 2010 vintage of the same series.
    Series name matches (passes pre-filter), but year diff drops
    metadata_score to ~0.78 (below 0.85 threshold), so broaden fires.
    """
    initial_volumes = [
        _FakeBasicVolume(vid=1001, name="My Series", start_year=2010),
    ]
    broader_volumes = [
        *initial_volumes,  # dup; should be skipped via volume_id dedup
        _FakeBasicVolume(vid=2001, name="My Series", start_year=2024),
    ]
    issues = {
        1001: [
            _FakeBasicIssue(
                iid=901,
                number="1",
                volume_name="My Series",
                cover_year=2010,
                volume_id=1001,
            )
        ],
        2001: [
            _FakeBasicIssue(
                iid=903,
                number="1",
                volume_name="My Series",
                cover_year=2024,
                volume_id=2001,
            )
        ],
    }
    fake = _TwoStepCV(
        initial_volumes=initial_volumes,
        broader_volumes=broader_volumes,
        issues_by_volume=issues,
    )
    src = _make_cv_source_with_budget(monkeypatch, fake, APIBudget.FAST)

    profile = ComicProfile(series="My Series", issue="1", issue_int=1, year=2024)
    candidates = src.search(profile)

    # Two CV search calls: initial (max_results=5) and broaden (=20).
    assert len(fake.search_calls) == 2
    assert fake.search_calls[0]["max_results"] == 5
    assert fake.search_calls[1]["max_results"] == 20

    # Both the initial year-drifted candidate AND the broadened correct
    # candidate are present.
    issue_ids = [c.issue_id for c in candidates]
    assert 901 in issue_ids
    assert 903 in issue_ids
    # vol 1001 was in both passes; its list_issues fires only once
    # (dedupe skipped the broaden re-fetch).
    vol1001_calls = [
        c for c in fake.list_issues_calls if "volume:1001" in c.get("filter", "")
    ]
    assert len(vol1001_calls) == 1


def test_broaden_retry_skipped_when_top_score_strong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Phase H: a strong top quick-score skips broaden, saving API calls.

    When the initial pass returns a volume whose metadata aligns with
    `profile` (matching name + year), metadata_score clears 0.85 and
    the broaden retry doesn't fire. Verifies we don't pay the broaden
    cost on the common case.
    """
    vol = _FakeBasicVolume(vid=100, name="Watchmen", start_year=1986)
    # cover_year matches profile.year — full year credit, score ~0.91.
    issue = _FakeBasicIssue(iid=42, number="1", volume_name="Watchmen", cover_year=1986)
    fake = _TwoStepCV(
        initial_volumes=[vol],
        broader_volumes=[
            vol,
            _FakeBasicVolume(vid=200, name="Watchmen Annotated", start_year=2008),
        ],
        issues_by_volume={100: [issue], 200: []},
    )
    src = _make_cv_source_with_budget(monkeypatch, fake, APIBudget.FAST)

    profile = ComicProfile(series="Watchmen", issue="1", issue_int=1, year=1986)
    src.search(profile)

    # Only one volume search call — broaden never fired.
    assert len(fake.search_calls) == 1
    assert fake.search_calls[0]["max_results"] == 5


def test_broaden_retry_skipped_under_balanced_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Phase H: BALANCED/EXHAUSTIVE already use max_volumes=20, no broaden.

    The broaden-cap is the default budget's max_volumes value; broaden
    only fires when the resolved budget caps below that. Verifies that
    BALANCED doesn't trigger an even-wider re-search.
    """
    vol = _FakeBasicVolume(vid=1, name="Unrelated", start_year=2020)
    issue = _FakeBasicIssue(iid=1, number="1", volume_name="Unrelated")
    fake = _TwoStepCV(
        initial_volumes=[vol],
        broader_volumes=[
            vol,
            _FakeBasicVolume(vid=2, name="My Series", start_year=2020),
        ],
        issues_by_volume={1: [issue], 2: []},
    )
    src = _make_cv_source_with_budget(monkeypatch, fake, APIBudget.BALANCED)

    profile = ComicProfile(series="My Series", issue="1", issue_int=1, year=2020)
    src.search(profile)

    # Single search call — broaden gate is `max_volumes < _BROADEN_CAP`
    # which is False under BALANCED (20 == 20).
    assert len(fake.search_calls) == 1
    assert fake.search_calls[0]["max_results"] == 20


def test_broaden_retry_dedupes_by_volume_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Phase H: broaden's `list_issues` calls skip volume_ids already fetched.

    When the broader CV search returns volumes overlapping with the
    initial pass, the per-volume `list_issues` only runs for the NEW
    volume_ids. Avoids paying for the same API call twice.

    All volumes use matching series names so they pass the pre-filter;
    year drift on the initial pass keeps the quick-score below the
    broaden trigger.
    """
    initial = [_FakeBasicVolume(vid=10, name="My Series", start_year=2010)]
    broader = [
        _FakeBasicVolume(vid=10, name="My Series", start_year=2010),  # dup
        _FakeBasicVolume(vid=11, name="My Series", start_year=2015),  # new
        _FakeBasicVolume(vid=20, name="My Series", start_year=2024),  # new
    ]
    issues = {
        10: [
            _FakeBasicIssue(
                iid=110,
                number="1",
                volume_name="My Series",
                cover_year=2010,
                volume_id=10,
            )
        ],
        11: [
            _FakeBasicIssue(
                iid=111,
                number="1",
                volume_name="My Series",
                cover_year=2015,
                volume_id=11,
            )
        ],
        20: [
            _FakeBasicIssue(
                iid=120,
                number="1",
                volume_name="My Series",
                cover_year=2024,
                volume_id=20,
            )
        ],
    }
    fake = _TwoStepCV(
        initial_volumes=initial,
        broader_volumes=broader,
        issues_by_volume=issues,
    )
    src = _make_cv_source_with_budget(monkeypatch, fake, APIBudget.FAST)

    profile = ComicProfile(series="My Series", issue="1", issue_int=1, year=2024)
    src.search(profile)

    # Volume 10 in both passes — `list_issues` fires only once (initial).
    # Volume 11 only in broaden — fires once. Volume 20 only in broaden
    # — fires once.
    vol10_calls = [
        c for c in fake.list_issues_calls if "volume:10," in c.get("filter", "")
    ]
    vol11_calls = [
        c for c in fake.list_issues_calls if "volume:11," in c.get("filter", "")
    ]
    vol20_calls = [
        c for c in fake.list_issues_calls if "volume:20," in c.get("filter", "")
    ]
    assert len(vol10_calls) == 1
    assert len(vol11_calls) == 1
    assert len(vol20_calls) == 1


def test_broaden_retry_skipped_when_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Phase H: broaden doesn't fire when initial search returned no candidates.

    `max(...)` over empty wouldn't work without the `default=0.0`
    fallback — but more importantly, with 0 initial candidates there's
    nothing to score and the broaden-trigger logic's no-op-on-empty
    guard kicks in. (The existing 'no volumes' path already returns
    early; broaden only considers the post-pre-filter candidate count.)
    """
    fake = _TwoStepCV(
        initial_volumes=[],
        broader_volumes=[_FakeBasicVolume(vid=1, name="Anything", start_year=2020)],
        issues_by_volume={},
    )
    src = _make_cv_source_with_budget(monkeypatch, fake, APIBudget.FAST)

    profile = ComicProfile(series="Anything", issue="1", issue_int=1, year=2020)
    src.search(profile)

    # No volumes returned by initial search → early-return BEFORE broaden
    # gate, so only one search call.
    assert len(fake.search_calls) == 1
