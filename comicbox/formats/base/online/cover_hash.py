"""
Cover-hash primitives and the matcher's hashing-invocation policy.

pHash via the `imagehash` library (8x8 = 64 bits). Mokkari already
returns a precomputed pHash in `Issue.cover_hash`, so for Metron
candidates we string-compare. ComicVine and GCD candidates require
downloading the cover image — that's M6's concern.

The matcher invocation policy decides *when* hashing runs:

- Skip when the top metadata score is unambiguous (clears
  `confidence_threshold` AND well-separated from runner-up).
- Hash top K candidates when uncertain or close-call.
- Skip when nothing clears `min_confidence` (hashing won't save it).
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from imagehash import ImageHash

# pHash is an 8x8 = 64 bit hash. Keep this constant for clarity in the
# distance calculation.
HASH_BITS = 64


def compute_phash(image_bytes: bytes) -> str:
    """Return the pHash of an image as a hex string."""
    from imagehash import phash
    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as img:
        return str(phash(img))


def parse_hash(hex_str: str) -> ImageHash:
    """Parse a hex-encoded pHash string back into an ImageHash."""
    from imagehash import hex_to_hash

    return hex_to_hash(hex_str)


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two hex-encoded pHash strings."""
    return parse_hash(a) - parse_hash(b)


def cover_score(local_hash: str, candidate_hash: str) -> float:
    """
    Convert a Hamming distance into a [0, 1] similarity score.

    `s_cover = 1 - (hamming / 64)`. Clamped to [0, 1] for safety.
    """
    distance = hamming_distance(local_hash, candidate_hash)
    raw = 1.0 - (distance / HASH_BITS)
    return max(0.0, min(1.0, raw))


# ----------------------------------------------------- cover-hash URL cache
# Generic infrastructure (serves any source whose candidates carry cover
# URLs: ComicVine today, GCD later) — lives here beside compute_phash, not
# in a format package.


class CoverHashUrlCache:
    """
    Tiny SQLite cache mapping cover URLs to their pHash strings.

    Holds ONE connection for its lifetime rather than reconnecting per
    call. The matcher hashes up to 15 candidates per ambiguous comic, so
    the old reconnect-per-`get`/`set` cost two fresh connections per
    candidate — pure overhead on the hot path. `check_same_thread=False`
    plus `_lock` keeps that single connection safe for the cover-fetch
    pool's workers and for `-j N` boxes sharing one cache object.
    """

    # SQLite's default SQLITE_MAX_VARIABLE_NUMBER is 999 on older builds;
    # chunk `IN (...)` lookups well under it.
    _MAX_VARS = 500

    def __init__(self, db_path: Any) -> None:
        """Open / create the sqlite cache file at `db_path`."""
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = self._connect()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS cover_hashes "
                "(url TEXT PRIMARY KEY, phash TEXT NOT NULL)"
            )
        # Insert-or-replace only, so this rarely accumulates free pages, but
        # reclaim them if it ever does (e.g. churned cover URLs). Runs on a
        # separate connection — VACUUM cannot run inside a transaction.
        from comicbox.formats.base.online.vacuum import vacuum_if_bloated

        vacuum_if_bloated(self._db_path)

    def _connect(self) -> sqlite3.Connection:
        # Serialized by `_lock`, so the same connection is safe to hand to
        # the cover-fetch pool's worker threads.
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def get(self, url: str) -> str | None:
        """Return the cached pHash for a cover URL, or None if absent."""
        return self.get_many((url,)).get(url)

    def get_many(self, urls: Sequence[str]) -> dict[str, str]:
        """
        Return the cached pHash for every URL that has one.

        One query per chunk instead of one connection per URL — the
        batch cover-fetch path resolves a whole top-K set in a single
        round-trip against the cache before any download starts.
        """
        wanted = [u for u in dict.fromkeys(urls) if u]
        if not wanted:
            return {}
        found: dict[str, str] = {}
        with self._lock:
            for i in range(0, len(wanted), self._MAX_VARS):
                chunk = wanted[i : i + self._MAX_VARS]
                placeholders = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT url, phash FROM cover_hashes WHERE url IN ({placeholders})",  # noqa: S608 — placeholders only, values are bound
                    chunk,
                ).fetchall()
                found.update({row[0]: row[1] for row in rows})
        return found

    def set(self, url: str, phash: str) -> None:
        """Store a pHash for a cover URL, overwriting any previous value."""
        self.set_many(((url, phash),))

    def set_many(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Store many URL → pHash mappings in one transaction."""
        rows = [(url, phash) for url, phash in pairs if url and phash]
        if not rows:
            return
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO cover_hashes(url, phash) VALUES (?, ?)",
                rows,
            )

    def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        with self._lock:
            # sqlite3's close() is itself a no-op once closed, so the
            # connection can stay non-optional and every reader avoids a
            # None check on the hot path.
            self._conn.close()


# Cap on concurrent cover downloads. The matcher hashes up to 15
# candidates (`_top_k_for_hashing`), so 8 clears a full top-K in two
# waves. These GETs hit the sources' image CDNs, NOT their rate-limited
# API hosts, so they are not governed by simyan/mokkari's limiters — but
# a burst is still multiplied by `-j N` workers, so keep it modest.
MAX_COVER_FETCH_WORKERS = 8

_COVER_FETCH_TIMEOUT_S = 15.0


class CoverFetchPool:
    """
    Downloads cover images concurrently and returns their pHashes.

    Owns ONE `httpx.Client` for its lifetime, so a top-K batch reuses
    pooled connections instead of paying a TCP+TLS handshake per
    candidate. Failures are logged and dropped exactly as the serial
    path did — a cover that won't download is a missing signal, never a
    failed lookup.
    """

    def __init__(self, max_workers: int = MAX_COVER_FETCH_WORKERS) -> None:
        """Record the worker ceiling; the HTTP client is built on first use."""
        self._max_workers = max(1, max_workers)
        self._client: Any = None
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import httpx

                    self._client = httpx.Client(
                        timeout=_COVER_FETCH_TIMEOUT_S, follow_redirects=True
                    )
        return self._client

    def fetch_hash(self, url: str) -> str | None:
        """Download one cover and return its pHash, or None on any failure."""
        try:
            response = self._get_client().get(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"online: cover download failed ({url}): {exc}")
            return None
        try:
            return compute_phash(response.content)
        except Exception as exc:
            logger.warning(f"online: cover pHash failed ({url}): {exc}")
            return None

    def fetch_hashes(self, urls: Sequence[str]) -> dict[str, str]:
        """
        Download many covers concurrently; return `{url: phash}` for the wins.

        URLs that fail to download or hash are simply absent from the
        result. Order is irrelevant — the caller maps back by URL.
        """
        unique = [u for u in dict.fromkeys(urls) if u]
        if not unique:
            return {}
        if len(unique) == 1:
            phash = self.fetch_hash(unique[0])
            return {unique[0]: phash} if phash else {}
        workers = min(self._max_workers, len(unique))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            hashes = zip(unique, executor.map(self.fetch_hash, unique), strict=True)
            return {url: phash for url, phash in hashes if phash}

    def close(self) -> None:
        """Close the HTTP client. Safe to call more than once."""
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
