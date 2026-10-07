"""
Cover-hash primitives and the matcher's hashing-invocation policy.

pHash (8x8 = 64 bits), computed in pure Python bit for bit the way
`imagehash.phash` computes it, because Metron's precomputed hashes
(`Issue.cover_hash`, returned by Mokkari) come from imagehash and are
string-compared against ours. ComicVine and GCD candidates require
downloading the cover image — that's M6's concern.

The matcher invocation policy decides *when* hashing runs:

- Skip when the top metadata score is unambiguous (clears
  `confidence_threshold` AND well-separated from runner-up).
- Hash top K candidates when uncertain or close-call.
- Skip when nothing clears `min_confidence` (hashing won't save it).
"""

from __future__ import annotations

import cmath
import math
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from PIL.Image import Image as PILImage

# imagehash's phash defaults: hash_size=8, highfreq_factor=4. Shrink the
# cover to 32x32 grayscale, DCT both axes, keep the low-frequency 8x8.
_HASH_SIDE = 8
_DCT_SIDE = _HASH_SIDE * 4
# pHash is an 8x8 = 64 bit hash. Keep this constant for clarity in the
# distance calculation.
HASH_BITS = _HASH_SIDE * _HASH_SIDE
_HEX_DIGITS = HASH_BITS // 4
_HEX_HASH_RE = re.compile(rf"[0-9a-fA-F]{{{_HEX_DIGITS}}}")

# FFT twiddle factors for every power-of-two length up to _DCT_SIDE, and
# the DCT post-twiddle. Built once; the expressions are written exactly as
# below on purpose — a different but equivalent formula can round
# differently and flip a bit near the median.
_FFT_TWIDDLES = {
    n: tuple(cmath.exp(-2j * math.pi * k / n) for k in range(n // 2))
    for n in (1 << p for p in range(1, _DCT_SIDE.bit_length()))
}
_DCT_TWIDDLES = tuple(
    cmath.exp(-1j * math.pi * k / (2 * _DCT_SIDE)) for k in range(_DCT_SIDE)
)


def _fft(values: list[complex]) -> list[complex]:
    """Radix-2 FFT. `len(values)` must be a power of two."""
    n = len(values)
    if n == 1:
        return values
    even = _fft(values[0::2])
    odd = _fft(values[1::2])
    twiddles = _FFT_TWIDDLES[n]
    half = n // 2
    out = [0j] * n
    for k in range(half):
        t = twiddles[k] * odd[k]
        out[k] = even[k] + t
        out[k + half] = even[k] - t
    return out


def _dct2(values: Sequence[float]) -> list[float]:
    """
    Unnormalized DCT-II, equal to `scipy.fftpack.dct(values)`.

    Makhoul's reordering turns it into one same-length FFT. Do not
    replace this with the direct cosine sum: the butterflies cancel equal
    inputs exactly, as scipy's FFT does, so blank, flat and mirrored
    covers hash the same as imagehash. A direct sum leaves rounding noise
    around the median and flips bits on exactly those images.
    """
    n = _DCT_SIDE
    reordered = [0j] * n
    for i in range(n // 2):
        reordered[i] = complex(values[2 * i])
        reordered[n - 1 - i] = complex(values[2 * i + 1])
    spectrum = _fft(reordered)
    return [2.0 * (_DCT_TWIDDLES[k] * spectrum[k]).real for k in range(n)]


def phash_int(image: PILImage) -> int:
    """Return the 64-bit pHash of an image, as `imagehash.phash` computes it."""
    from PIL import Image

    side = _DCT_SIDE
    gray = image.convert("L").resize((side, side), Image.Resampling.LANCZOS)
    pixels = gray.tobytes()  # row-major: pixels[y * side + x]
    # DCT down each column (numpy axis 0)...
    columns = [_dct2([pixels[y * side + x] for y in range(side)]) for x in range(side)]
    # ...then along the low-frequency rows (axis 1), keeping the 8x8 corner.
    low: list[float] = []
    for k in range(_HASH_SIDE):
        low.extend(_dct2([column[k] for column in columns])[:_HASH_SIDE])
    ordered = sorted(low)
    mid = len(ordered) // 2
    median = (ordered[mid - 1] + ordered[mid]) / 2.0  # numpy.median, even count
    bits = 0
    for value in low:  # row-major, so the DC term is the top bit
        bits = (bits << 1) | int(value > median)
    return bits


def compute_phash(image_bytes: bytes) -> str:
    """Return the pHash of an image as a 16-digit lowercase hex string."""
    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as img:
        return f"{phash_int(img):0{_HEX_DIGITS}x}"


def parse_hash(hex_str: str) -> int:
    """Parse a hex-encoded pHash string into its 64-bit integer."""
    if not _HEX_HASH_RE.fullmatch(hex_str):
        reason = f"not a {HASH_BITS}-bit hex pHash: {hex_str!r}"
        raise ValueError(reason)
    return int(hex_str, 16)


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two hex-encoded pHash strings."""
    return (parse_hash(a) ^ parse_hash(b)).bit_count()


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
