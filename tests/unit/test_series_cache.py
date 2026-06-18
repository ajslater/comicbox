"""Tests for series-first batching — series_cache + lookup_issue warm path."""

from __future__ import annotations

from argparse import Namespace
from types import MappingProxyType

import pytest
from typing_extensions import override

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup, _series_fingerprint
from comicbox.events import AutoWritten, Event, SeriesIdentified
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.formats.sources import MetadataSources

# --- fingerprint ------------------------------------------------------------


def test_series_fingerprint_is_deterministic() -> None:
    """Same series-level inputs → same fingerprint."""
    p1 = ComicProfile(series="Spider-Man", year=2018, publisher="Marvel")
    p2 = ComicProfile(series="Spider-Man", year=2018, publisher="Marvel")
    assert _series_fingerprint(p1) == _series_fingerprint(p2)


def test_series_fingerprint_normalizes_case_and_spaces() -> None:
    """Case + surrounding whitespace shouldn't fork the cache key."""
    p1 = ComicProfile(series="Spider-Man", year=2018, publisher="Marvel")
    p2 = ComicProfile(series="  SPIDER-MAN  ", year=2018, publisher="marvel")
    assert _series_fingerprint(p1) == _series_fingerprint(p2)


def test_series_fingerprint_differs_across_series() -> None:
    p1 = ComicProfile(series="Spider-Man", year=2018, publisher="Marvel")
    p2 = ComicProfile(series="Batman", year=2018, publisher="DC")
    assert _series_fingerprint(p1) != _series_fingerprint(p2)


def test_series_fingerprint_ignores_issue_level_fields() -> None:
    """Different issues of the same series share a fingerprint."""
    p1 = ComicProfile(series="Spider-Man", issue="1", year=2018, publisher="Marvel")
    p2 = ComicProfile(series="Spider-Man", issue="2", year=2018, publisher="Marvel")
    assert _series_fingerprint(p1) == _series_fingerprint(p2)


# --- mock source ------------------------------------------------------------


def _candidate_payload(issue_id: int) -> dict:
    return {
        "id": issue_id,
        "number": "5",
        "cover_date": "2020-04-01",
        "modified": "2020-04-02T12:00:00Z",
        "publisher": {"id": 1, "name": "Pub"},
        "series": {"id": 1, "name": "S", "year_began": 2020, "volume": 1},
    }


class _CountingMetron:
    """Mock source that tracks search() and lookup_issue() invocations."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings, candidates) -> None:
        self._credentials = credentials
        self._candidates = candidates
        self.search_calls = 0
        self.lookup_calls: list[tuple[int, str | None]] = []
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return bool(self._credentials.user and self._credentials.password)

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return _candidate_payload(issue_id)

    def search(self, profile):
        self.search_calls += 1
        return list(self._candidates)

    def lookup_issue(self, volume_id: int, issue_number):
        self.lookup_calls.append((volume_id, issue_number))
        # Return the first candidate whose volume_id matches; else None.
        for c in self._candidates:
            if c.volume_id == volume_id:
                return c
        return None


def _make_candidate(issue_id: int, volume_id: int) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series="Foo Comics",
            issue="5",
            year=2020,
            publisher="Quality Comics",
            page_count=24,
            cover_url=None,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


def _patch_source(monkeypatch, candidates):
    instances: list[_CountingMetron] = []

    def factory(creds, settings):
        s = _CountingMetron(creds, settings, candidates)
        instances.append(s)
        return s

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _build_cb() -> Comicbox:
    cli_md = {
        "comicbox": {
            "series": {"name": "Foo Comics"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
            "publisher": {"name": "Quality Comics"},
            "page_count": 24,
        }
    }
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            general=Namespace(metadata=cli_md),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    return Comicbox(config=args)


# --- warm-path behaviour ----------------------------------------------------


def test_cold_path_populates_series_cache(monkeypatch) -> None:
    """Cold-path AUTO_WRITE populates the cache + fires SeriesIdentified."""
    _patch_source(monkeypatch, [_make_candidate(101, volume_id=42)])
    cache: dict = {}
    events: list[Event] = []
    cb = _build_cb()
    cb.set_series_cache(cache)
    cb.set_event_handler(events.append)
    cb.run_online_lookup()

    fp = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    assert cache[("metron", fp)] == 42
    si = [e for e in events if isinstance(e, SeriesIdentified)]
    assert len(si) == 1
    assert si[0].volume_id == 42
    assert si[0].source == "metron"


def test_warm_path_uses_lookup_issue_not_search(monkeypatch) -> None:
    """When cache is preloaded, the warm path bypasses search()."""
    instances = _patch_source(monkeypatch, [_make_candidate(101, volume_id=42)])
    fp = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    cache = {("metron", fp): 42}
    events: list[Event] = []
    cb = _build_cb()
    cb.set_series_cache(cache)
    cb.set_event_handler(events.append)
    cb.run_online_lookup()

    src = instances[0]
    assert src.search_calls == 0
    assert src.lookup_calls == [(42, "5")]
    auto = [e for e in events if isinstance(e, AutoWritten)]
    assert len(auto) == 1


def test_warm_path_falls_back_to_search_on_miss(monkeypatch) -> None:
    """Cached volume_id with no matching issue → fall back to search."""

    class _StaleMetron(_CountingMetron):
        @override
        def lookup_issue(self, volume_id, issue_number):
            # Pretend the cached volume_id is stale — no match here.
            self.lookup_calls.append((volume_id, issue_number))

    instances: list = []

    def factory(creds, settings):
        s = _StaleMetron(creds, settings, [_make_candidate(101, 42)])
        instances.append(s)
        return s

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    fp = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    cache: dict = {("metron", fp): 999}  # stale volume_id
    cb = _build_cb()
    cb.set_series_cache(cache)
    cb.run_online_lookup()
    src = instances[0]
    # lookup_issue tried, returned None; search() then fired as fallback.
    assert src.lookup_calls == [(999, "5")]
    assert src.search_calls == 1
    # Cache untouched — first-writer-wins keeps the stale entry. The
    # bigger refactor in plan §3.10 would mark it ambiguous; v1 keeps
    # the simple "leave it alone" invariant.
    assert cache[("metron", fp)] == 999


def test_setdefault_first_writer_wins(monkeypatch) -> None:
    """A second cold-path acceptance does NOT overwrite an existing entry."""
    _patch_source(monkeypatch, [_make_candidate(101, volume_id=42)])
    fp = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    cache: dict = {("metron", fp): 99}  # prior writer's value
    cb = _build_cb()
    cb.set_series_cache(cache)
    cb.run_online_lookup()
    # The cold-path search ran (cached volume 99 ≠ candidate's 42 = ok),
    # but the cache entry should remain at 99 — _maybe_populate_series_cache
    # treats existing keys as immutable.
    # NB: in this scenario the warm path actually fires first and may
    # short-circuit to lookup_issue(99, ...). Our mock returns the
    # candidate whose volume_id matches — volume_id=42 ≠ 99, so it
    # returns None; falls back to search.
    assert cache[("metron", fp)] == 99


def test_rematch_bypasses_series_cache(monkeypatch) -> None:
    """--rematch skips the warm path — consistent with stored-id behavior."""
    instances = _patch_source(monkeypatch, [_make_candidate(101, volume_id=42)])
    fp = _series_fingerprint(
        ComicProfile(series="Foo Comics", year=2020, publisher="Quality Comics")
    )
    cache: dict = {("metron", fp): 42}
    cli_md = {
        "comicbox": {
            "series": {"name": "Foo Comics"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
            "publisher": {"name": "Quality Comics"},
            "page_count": 24,
        }
    }
    args = Namespace(
        comicbox=Namespace(
            online_sources=["metron"],
            rematch=True,
            general=Namespace(metadata=cli_md),
            auth=["metron:user=u", "metron:pass=p"],
        )
    )
    cb = Comicbox(config=args)
    cb.set_series_cache(cache)
    cb.run_online_lookup()
    src = instances[0]
    # search() ran (rematch); lookup_issue() did NOT.
    assert src.search_calls == 1
    assert src.lookup_calls == []


def test_no_cache_keeps_existing_behavior(monkeypatch) -> None:
    """When set_series_cache is never called the matcher runs as before."""
    instances = _patch_source(monkeypatch, [_make_candidate(101, volume_id=42)])
    cb = _build_cb()
    # No cb.set_series_cache(...) call.
    cb.run_online_lookup()
    src = instances[0]
    assert src.search_calls == 1
    assert src.lookup_calls == []


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
