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
from contextlib import closing
from io import BytesIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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
    """Tiny SQLite cache mapping cover URLs to their pHash strings."""

    def __init__(self, db_path: Any) -> None:
        """Open / create the sqlite cache file at `db_path`."""
        self._db_path = str(db_path)
        # `with conn:` only manages the transaction; sqlite3 context managers
        # never close the connection, so closing() is needed to avoid leaking
        # one per call (each method reconnects to stay thread-safe under -j).
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cover_hashes "
                "(url TEXT PRIMARY KEY, phash TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get(self, url: str) -> str | None:
        """Return the cached pHash for a cover URL, or None if absent."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT phash FROM cover_hashes WHERE url = ?", (url,)
            ).fetchone()
        return row[0] if row else None

    def set(self, url: str, phash: str) -> None:
        """Store a pHash for a cover URL, overwriting any previous value."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO cover_hashes(url, phash) VALUES (?, ?)",
                (url, phash),
            )
