#!/usr/bin/env python3
"""
Rebuild the macOS resource-fork test fixture from the Captain Science pages.

``macos_resource_fork.cbz`` mimics a Finder-compressed comic: the real page
JPEGs sit at the top level next to a ``__MACOSX/`` folder holding one AppleDouble
``._`` resource-fork sidecar per page. The fixture exists so
``tests/test_pages.py::test_ignore_macos_resource_forks`` can assert that the
sidecars (and the ``__MACOSX`` folder) are skipped, leaving ``page_count == 2``.

The two pages are reused from ``Captain Science 001/`` -- already downsized to
thumbnails by ``create_cs_archives.py`` -- so the fixture stays a few KB. The
downsize step here is idempotent, so it also works against full-size sources.

Run from anywhere: ``python tests/files/create_macos_resource_fork.py``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
SRC = HERE / "Captain Science 001"
OUT = HERE / "macos_resource_fork.cbz"

# The first two Captain Science pages become the archive's real pages.
PAGE_NAMES = ("CaptainScience#1_01.jpg", "CaptainScience#1_02.jpg")
MACOSX_DIR = "__MACOSX/"

THUMB_SIZE = 160
JPEG_QUALITY = 30

# Fixed entry timestamp so the rebuilt fixture is reproducible.
FIXED_DT = (2026, 5, 17, 21, 43, 38)


def _thumb(data: bytes) -> bytes:
    """Downsize a page JPEG to a thumbnail (idempotent)."""
    with Image.open(io.BytesIO(data)) as im:
        if max(im.size) <= THUMB_SIZE:
            return data
        im.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="jpeg", quality=JPEG_QUALITY)
    return buf.getvalue()


def _write(zf: zipfile.ZipFile, arcname: str, data: bytes, compress_type: int) -> None:
    """Add one entry with a fixed timestamp and explicit compression."""
    info = zipfile.ZipInfo(arcname, date_time=FIXED_DT)
    info.compress_type = compress_type
    zf.writestr(info, data)


def build() -> None:
    """Write macos_resource_fork.cbz with its resource-fork scaffolding."""
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in PAGE_NAMES:
            _write(zf, name, _thumb((SRC / name).read_bytes()), zipfile.ZIP_DEFLATED)
        # AppleDouble scaffolding comicbox must ignore: the __MACOSX folder and
        # an empty ._ sidecar per page.
        _write(zf, MACOSX_DIR, b"", zipfile.ZIP_STORED)
        for name in PAGE_NAMES:
            _write(zf, f"{MACOSX_DIR}._{name}", b"", zipfile.ZIP_STORED)


def main() -> None:
    build()
    print(f"{OUT.stat().st_size:>8} bytes  {OUT.name}")


if __name__ == "__main__":
    main()
