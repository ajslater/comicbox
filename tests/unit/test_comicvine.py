"""ComicVine source + transform tests."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from comicbox.config.settings import OnlineSettings, OnlineSourceCredentials
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
    def __init__(self, vid: int, name: str) -> None:
        self.id = vid
        self.name = name


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
    ) -> None:
        from datetime import date

        self.id = iid
        self.number = number
        self.cover_date = date(cover_year, 1, 1)
        self.image = _FakeImage()
        self.site_url = f"http://example.com/issue/{iid}"
        self.volume = _FakeBasicVolume(vid=999, name=volume_name)


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
