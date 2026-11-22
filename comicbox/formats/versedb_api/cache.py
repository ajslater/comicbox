"""
A small sqlite cache of VerseDB's 200 responses.

mokkari and simyan each bring a response cache; the `versedb` SDK brings
none, and the ``--cache`` modes have to work for every source. AJ asked for
as much caching as possible (2026-11-21): the free tier allows 300 requests
an hour, so every repeat call answered from here is budget kept.

The mode policy (off, refresh's wipe-once, ttl) is the shared
`OnlineSource._resolve_response_cache`; this class only stores. A ttl of 0
means keep forever, as both other sources treat it; ``cache.mode: off`` is
the switch for not caching at all.

Connection handling follows `CoverHashUrlCache`: one connection opened with
``check_same_thread=False``, every access under a lock, `vacuum_if_bloated`
on open, and an explicit `close`.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import TYPE_CHECKING

from comicbox.formats.base.online.vacuum import vacuum_if_bloated

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path


class ResponseCache:
    """Response bodies keyed by request, each stamped with when it was stored."""

    def __init__(self, path: Path, ttl: timedelta) -> None:
        """Open or create the cache file and drop what has expired."""
        self._path = str(path)
        self._ttl_s = ttl.total_seconds()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS responses "
                "(key TEXT PRIMARY KEY, stored_at REAL NOT NULL, body BLOB NOT NULL)"
            )
            if self._ttl_s > 0:
                # Expired rows are never read again; without this the file
                # would only grow.
                self._conn.execute(
                    "DELETE FROM responses WHERE stored_at < ?",
                    (time.time() - self._ttl_s,),
                )
        # A separate connection: VACUUM cannot run inside a transaction.
        vacuum_if_bloated(self._path)

    def get(self, key: str) -> bytes | None:
        """Return the stored body for ``key``, or None when absent or expired."""
        with self._lock:
            row = self._conn.execute(
                "SELECT stored_at, body FROM responses WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        stored_at, body = row
        if self._ttl_s > 0 and stored_at + self._ttl_s < time.time():
            return None
        return bytes(body)

    def set(self, key: str, body: bytes) -> None:
        """Store ``body`` for ``key``, replacing what was there."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (key, stored_at, body) "
                "VALUES (?, ?, ?)",
                (key, time.time(), body),
            )

    def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        with self._lock:
            self._conn.close()
