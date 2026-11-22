"""
A small sqlite cache of VerseDB's 200 responses.

mokkari and simyan each bring a response cache; the `versedb` SDK brings
none, and the ``--cache`` modes have to work for every source. AJ asked for
as much caching as possible (2026-11-21): the free tier allows 300 requests
an hour, so every repeat call answered from here is budget kept.

The mode policy (off, refresh's wipe-once, ttl) is the shared
`OnlineSource._resolve_response_cache`; this class only stores. A ttl of 0
means keep forever, as both other sources treat it; ``cache.mode: off`` is
the switch for not caching at all. A row's expiry is fixed when it is
stored, so a caller can keep some answers for less: an empty result is kept
for a day, as Metron's are, so an issue VerseDB adds tomorrow is found.

The cache is an optimization, so it never fails a request. A read that
errors is a miss and a write that errors is skipped, each warned once: the
CLI and Codex can share the file, and "database is locked" must not throw
away a response already paid for. `open_response_cache` rebuilds a file that
is corrupt or not sqlite at all, and runs uncached when even that fails.

Connection handling follows `CoverHashUrlCache`: one connection opened with
``check_same_thread=False``, every access under a lock, `vacuum_if_bloated`
on open, and an explicit `close`.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Final

from loguru import logger

from comicbox.formats.base.online.vacuum import vacuum_if_bloated
from comicbox.formats.base.online.warn_once import warn_once

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path

_SOURCE: Final = "versedb"
_COLUMNS: Final = ("key", "expires_at", "body")


class ResponseCache:
    """Response bodies keyed by request, each stamped with when it expires."""

    def __init__(self, path: Path, ttl: timedelta) -> None:
        """Open or create the cache file and drop what has expired."""
        self._path = str(path)
        self._ttl_s = ttl.total_seconds()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        try:
            self._create()
        except sqlite3.Error:
            # Never leave the connection to the finalizer.
            self._conn.close()
            raise
        # A separate connection: VACUUM cannot run inside a transaction.
        vacuum_if_bloated(self._path)

    def _create(self) -> None:
        with self._lock, self._conn:
            columns = tuple(
                row[1] for row in self._conn.execute("PRAGMA table_info(responses)")
            )
            if columns and columns != _COLUMNS:
                # A layout this version doesn't write; it is only a cache.
                self._conn.execute("DROP TABLE responses")
            # expires_at is NULL for a row kept forever.
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS responses "
                "(key TEXT PRIMARY KEY, expires_at REAL, body BLOB NOT NULL)"
            )
            # Expired rows are never read again; without this the file would
            # only grow.
            self._conn.execute(
                "DELETE FROM responses WHERE expires_at < ?", (time.time(),)
            )

    def get(self, key: str) -> bytes | None:
        """Return the stored body for ``key``, or None when absent, expired or unreadable."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT expires_at, body FROM responses WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as exc:
            warn_once(
                f"{_SOURCE}:cache-read",
                f"online {_SOURCE}: response cache unreadable, asking VerseDB "
                f"instead: {exc}",
            )
            return None
        if row is None:
            return None
        expires_at, body = row
        if expires_at is not None and expires_at < time.time():
            return None
        return bytes(body)

    def set(self, key: str, body: bytes, *, max_ttl: timedelta | None = None) -> None:
        """
        Store ``body`` for ``key``, replacing what was there; skip on error.

        ``max_ttl`` keeps this one row for less than the cache's ttl, and
        caps a keep-forever ttl too.
        """
        ttl_s = self._ttl_s
        if max_ttl is not None:
            cap_s = max_ttl.total_seconds()
            ttl_s = min(ttl_s, cap_s) if ttl_s > 0 else cap_s
        expires_at = time.time() + ttl_s if ttl_s > 0 else None
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO responses (key, expires_at, body) "
                    "VALUES (?, ?, ?)",
                    (key, expires_at, body),
                )
        except sqlite3.Error as exc:
            warn_once(
                f"{_SOURCE}:cache-write",
                f"online {_SOURCE}: response not cached ({exc}); the next "
                "identical request will be sent again",
            )

    def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        with self._lock:
            self._conn.close()


def _remove(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def open_response_cache(path: Path, ttl: timedelta) -> ResponseCache | None:
    """
    Open the response cache, or return None to run without one.

    comicbox owns this file, so one that is corrupt or not sqlite at all is
    deleted and rebuilt, as Metron's cache is. A file that is only busy
    ("database is locked", another process holding it) is left alone and the
    run goes uncached, rather than deleting what someone else has open.
    """
    try:
        return ResponseCache(path, ttl)
    except sqlite3.OperationalError as exc:
        warn_once(
            f"{_SOURCE}:cache-refused",
            f"online {_SOURCE}: running without a response cache: {exc}",
        )
        return None
    except sqlite3.DatabaseError:
        logger.warning(f"online {_SOURCE}: rebuilding unreadable cache {path}")
    _remove(path)
    try:
        return ResponseCache(path, ttl)
    except sqlite3.Error as exc:
        warn_once(
            f"{_SOURCE}:cache-refused",
            f"online {_SOURCE}: running without a response cache: {exc}",
        )
        return None
