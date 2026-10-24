"""
Metron's response cache against a real mokkari 5 `SqliteCache`.

The rest of the suite fakes the session or turns the cache off, which is
how the 4.x `SqliteCache(db_name=, expire=)` call outlived the keyword:
nothing built the cache a real run builds. These tests do.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import pytest
from loguru import logger
from mokkari.sqlite_cache import SqliteCache

from comicbox.config.online.settings import (
    CacheMode,
    OnlineCacheSettings,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.base.online import warn_once
from comicbox.formats.base.online.sources import base as sources_base
from comicbox.formats.metron_api import online_source as metron
from comicbox.formats.metron_api.online_source import MetronOnlineSource

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_EMPTY_LIST: Final = {"count": 0, "results": []}
_WEEK: Final = timedelta(days=7)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh shared sessions, refresh registry and warn-once keys per test."""
    monkeypatch.setattr(metron, "_session_cache", {})
    monkeypatch.setattr(metron, "_gate_cache", {})
    monkeypatch.setattr(sources_base, "_refreshed_cache_paths", set())
    monkeypatch.setattr(warn_once, "_seen", set())


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    yield messages
    logger.remove(handler_id)


def _source(
    tmp_path: Path, *, mode: CacheMode = CacheMode.ON, ttl: timedelta = _WEEK
) -> MetronOnlineSource:
    cache = OnlineCacheSettings(mode=mode, dir=tmp_path, ttl=ttl)
    return MetronOnlineSource(
        OnlineSourceCredentials(key="k"), OnlineSettings(cache=cache)
    )


def _open(source: MetronOnlineSource) -> SqliteCache:
    cache = source._get_cache()
    assert isinstance(cache, SqliteCache)
    return cache


def test_ttl_reaches_mokkari_as_a_timedelta(tmp_path: Path) -> None:
    """A sub-day TTL is kept as given, no longer rounded up to whole days."""
    with _open(_source(tmp_path, ttl=timedelta(hours=6))) as cache:
        policy = cache.ttl_policy
        assert policy.ttl_for("issue", "detail") == timedelta(hours=6)
        assert policy.ttl_for("series", "list") == timedelta(hours=6)


def test_zero_ttl_means_never_expire(tmp_path: Path) -> None:
    """`--cache-ttl 0` keeps entries forever, as in 4.x; it doesn't stop caching."""
    with _open(_source(tmp_path, ttl=timedelta(0))) as cache:
        assert cache.ttl_policy.ttl_for("issue", "detail") is SqliteCache.NEVER


def test_empty_searches_are_cached_for_a_day(tmp_path: Path) -> None:
    """
    An empty list is kept, so a batch from a series Metron lacks asks once.

    mokkari's default doesn't cache empty lists at all.
    """
    with _open(_source(tmp_path, ttl=timedelta(0))) as cache:
        ttl = cache.ttl_policy.ttl_for_value(
            _EMPTY_LIST, resource="series", kind="list"
        )
        assert ttl == timedelta(days=1)
    with _open(_source(tmp_path, ttl=timedelta(hours=1))) as cache:
        # Never longer than the TTL a non-empty list gets.
        ttl = cache.ttl_policy.ttl_for_value(
            _EMPTY_LIST, resource="series", kind="list"
        )
        assert ttl == timedelta(hours=1)


def test_cache_off_builds_no_cache(tmp_path: Path) -> None:
    assert _source(tmp_path, mode=CacheMode.OFF)._get_cache() is None


def test_a_corrupt_cache_file_is_rebuilt(tmp_path: Path, warnings: list[str]) -> None:
    source = _source(tmp_path)
    path = source.cache_db_path()
    path.write_bytes(b"not a sqlite database at all" * 64)
    path.with_name(path.name + "-wal").write_bytes(b"stale")

    with _open(source) as cache:
        cache.store("k", {"id": 1}, resource="issue", kind="detail")
        assert cache.get("k") == {"id": 1}
    assert any("rebuilding unreadable cache" in m for m in warnings)


def test_a_newer_mokkari_cache_is_left_alone(
    tmp_path: Path, warnings: list[str]
) -> None:
    """A file a newer mokkari wrote isn't wiped; the run goes uncached instead."""
    source = _source(tmp_path)
    path = source.cache_db_path()
    with closing(sqlite3.connect(path)) as con:
        con.execute("PRAGMA user_version = 999")
    before = path.read_bytes()

    assert source._get_cache() is None
    assert _source(tmp_path)._get_cache() is None

    assert path.read_bytes() == before
    assert sum("running without a response cache" in m for m in warnings) == 1


def test_refresh_clears_in_place_once_per_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    REFRESH empties the open database rather than unlinking it.

    Another process may hold it open in WAL mode, and unlinking the file
    under it strands the -wal and -shm files.
    """

    def no_unlink(_path: Path) -> None:
        reason = "Metron's refresh must not unlink the cache"
        raise AssertionError(reason)

    monkeypatch.setattr(sources_base, "refresh_cache_unlink_once", no_unlink)
    with _open(_source(tmp_path)) as cache:
        cache.store("stale", {"id": 1}, resource="issue", kind="detail")

    with _open(_source(tmp_path, mode=CacheMode.REFRESH)) as cache:
        assert cache.get("stale") is None
        cache.store("fresh", {"id": 2}, resource="issue", kind="detail")
    # A later source in the same run keeps what this run fetched.
    with _open(_source(tmp_path, mode=CacheMode.REFRESH)) as cache:
        assert cache.get("fresh") == {"id": 2}


def test_the_real_session_build_closes_its_cache(tmp_path: Path) -> None:
    """
    The production path: a real mokkari Session on a real cache.

    `close_shared_sessions()` releases the cache's connection, which
    `Session.close()` leaves open, and the cache reopens on next use.
    """
    session = _source(tmp_path)._get_session()
    cache = session.cache
    assert isinstance(cache, SqliteCache)
    assert cache._con is not None

    metron.close_shared_sessions()

    assert cache._con is None
    assert cache.get("anything") is None
    cache.close()
