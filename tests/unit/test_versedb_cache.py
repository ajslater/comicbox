"""The VerseDB response cache: hit, miss, ttl, keep-forever, reopen."""

from __future__ import annotations

import gc
import sqlite3
import warnings
from contextlib import closing
from datetime import timedelta
from typing import TYPE_CHECKING, Self

import pytest

from comicbox.formats.versedb_api.cache import ResponseCache, open_response_cache

if TYPE_CHECKING:
    from pathlib import Path


_CLOCK = "comicbox.formats.versedb_api.cache.time.time"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "versedb_cache.sqlite"


def test_miss_then_hit(path: Path) -> None:
    cache = ResponseCache(path, timedelta(days=7))
    try:
        assert cache.get("k") is None
        cache.set("k", b'{"data": 1}')
        assert cache.get("k") == b'{"data": 1}'
    finally:
        cache.close()


def test_a_row_expires_after_the_ttl(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_CLOCK, lambda: 1000.0)
    cache = ResponseCache(path, timedelta(seconds=60))
    try:
        cache.set("k", b"body")
        monkeypatch.setattr(_CLOCK, lambda: 1059.0)
        assert cache.get("k") == b"body"
        monkeypatch.setattr(_CLOCK, lambda: 1061.0)
        assert cache.get("k") is None
    finally:
        cache.close()


def test_a_zero_ttl_keeps_forever(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero means keep forever, as the other two sources read it."""
    monkeypatch.setattr(_CLOCK, lambda: 1000.0)
    cache = ResponseCache(path, timedelta(0))
    try:
        cache.set("k", b"body")
        monkeypatch.setattr(_CLOCK, lambda: 10.0**10)
        assert cache.get("k") == b"body"
    finally:
        cache.close()


def test_rows_outlive_the_connection(path: Path) -> None:
    cache = ResponseCache(path, timedelta(days=7))
    cache.set("k", b"body")
    cache.close()
    reopened = ResponseCache(path, timedelta(days=7))
    try:
        assert reopened.get("k") == b"body"
    finally:
        reopened.close()


def test_opening_drops_expired_rows(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_CLOCK, lambda: 1000.0)
    cache = ResponseCache(path, timedelta(seconds=60))
    cache.set("old", b"body")
    cache.close()
    monkeypatch.setattr(_CLOCK, lambda: 2000.0)
    ResponseCache(path, timedelta(seconds=60)).close()
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM responses").fetchone() == (0,)


def test_close_twice(path: Path) -> None:
    cache = ResponseCache(path, timedelta(days=7))
    cache.close()
    cache.close()


class _LockedConnection:
    """Stands in for a connection another process holds: every query fails."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object) -> None:
        msg = "database is locked"
        raise sqlite3.OperationalError(msg)

    def close(self) -> None:
        return None


def test_a_locked_cache_reads_as_a_miss_and_skips_the_store(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache error never reaches the retry layer."""
    cache = ResponseCache(path, timedelta(days=7))
    real = cache._conn
    monkeypatch.setattr(cache, "_conn", _LockedConnection())
    try:
        assert cache.get("k") is None
        cache.set("k", b"body")  # no raise
    finally:
        real.close()


def test_a_corrupt_file_is_rebuilt(path: Path) -> None:
    path.write_bytes(b"this is not a sqlite database" * 100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        cache = open_response_cache(path, timedelta(days=7))
        assert cache is not None
        try:
            cache.set("k", b"body")
            assert cache.get("k") == b"body"
        finally:
            cache.close()
        gc.collect()
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_an_unopenable_cache_runs_uncached_and_deletes_nothing(tmp_path: Path) -> None:
    """A path sqlite can't open is not ours to delete: run without a cache."""
    blocked = tmp_path / "versedb_cache.sqlite"
    blocked.mkdir()
    assert open_response_cache(blocked, timedelta(days=7)) is None
    assert blocked.is_dir()


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(days=7)])
def test_a_capped_row_expires_after_its_cap(
    path: Path, monkeypatch: pytest.MonkeyPatch, ttl: timedelta
) -> None:
    """An empty answer is kept a day, even by a keep-forever cache."""
    monkeypatch.setattr(_CLOCK, lambda: 1000.0)
    cache = ResponseCache(path, ttl)
    try:
        cache.set("empty", b'{"data": []}', max_ttl=timedelta(days=1))
        cache.set("full", b'{"data": [1]}')
        monkeypatch.setattr(_CLOCK, lambda: 1000.0 + 86_401)
        assert cache.get("empty") is None
        assert cache.get("full") == b'{"data": [1]}'
    finally:
        cache.close()


def test_an_older_table_layout_is_replaced(path: Path) -> None:
    """Only a cache: a layout this version doesn't write is dropped, not misread."""
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE responses (key TEXT PRIMARY KEY, stored_at REAL, body BLOB)"
        )
        conn.execute("INSERT INTO responses VALUES ('k', 1.0, x'00')")
    cache = ResponseCache(path, timedelta(days=7))
    try:
        assert cache.get("k") is None
        cache.set("k", b"body")
        assert cache.get("k") == b"body"
    finally:
        cache.close()
