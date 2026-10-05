"""
Real comic images from ``tests/files`` for the pHash tests.

Shared by ``test_cover_hash_parity``, which checks comicbox's pHash
against imagehash, and ``test_cover_hash``, which pins it to golden
values that need no imagehash.
"""

from __future__ import annotations

from functools import cache

from comicbox.box import Comicbox
from tests.const import TEST_CS_DIR, TEST_FILES_DIR

_ARCHIVE_SUFFIXES = frozenset({".cbz", ".pdf"})


def read_image(name: str) -> bytes:
    """
    Return the image ``name`` names, a path under ``tests/files``.

    An archive yields its cover the way the matcher reads it; a loose
    image file yields its bytes. An archive with no pages yields b"".
    """
    path = TEST_FILES_DIR / name
    if path.suffix not in _ARCHIVE_SUFFIXES:
        return path.read_bytes()
    with Comicbox(path) as car:
        return car.get_cover_page(pdf_format="pixmap", skip_metadata=True)


@cache
def real_images() -> dict[str, bytes]:
    """
    Every distinct real image, keyed by its path under ``tests/files``.

    The first pages of every CBZ and PDF, plus the loose Captain Science
    pages. Many archives share a cover, so identical images appear once,
    under the first name that has them.
    """
    paths = sorted(
        (*TEST_FILES_DIR.glob("*.cbz"), *TEST_FILES_DIR.rglob("*.pdf"))
    ) + sorted(TEST_CS_DIR.glob("*.jpg"))
    images: dict[str, bytes] = {}
    for path in paths:
        name = path.relative_to(TEST_FILES_DIR).as_posix()
        data = read_image(name)
        if data and data not in images.values():
            images[name] = data
    return images
