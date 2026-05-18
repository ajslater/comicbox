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

from io import BytesIO
from typing import TYPE_CHECKING

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
