"""The VerseDB response cache: hit, miss, ttl, keep-forever, reopen."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from comicbox.formats.versedb_api.cache import ResponseCache

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
