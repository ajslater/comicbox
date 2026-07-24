"""
Test converting pdfs to cbzs.

The synthetic fixtures mirror scanner output: each page is one
full-bleed jpeg, stored upside down with /Rotate 180 righting it at
display time. Conversion output must be readable by comic readers
(real image formats, nonzero page count) and match the *displayed*
orientation, not the stored one.
"""

from __future__ import annotations

import io
import zipfile
from argparse import Namespace
from typing import TYPE_CHECKING

import pymupdf
import pytest
from PIL import Image

from comicbox.box import Comicbox
from comicbox.config import get_config
from tests.const import TMP_ROOT_DIR
from tests.util.tmp import my_cleanup

if TYPE_CHECKING:
    from pathlib import Path

TMP_DIR = TMP_ROOT_DIR / __name__

CBZ_CONFIG = get_config(Namespace(comicbox=Namespace(convert=Namespace(cbz=True))))
CBZ_IMAGE_CONFIG = get_config(
    Namespace(comicbox=Namespace(convert=Namespace(cbz=True, pdf_pages="image")))
)

PAGE_COUNT = 2

#: Channel threshold separating the red half from the blue half after
#: jpeg compression (nominal values are 200 vs 50).
CHANNEL_THRESHOLD = 120


def _two_tone_jpeg() -> bytes:
    """Red top half, blue bottom half — makes orientation detectable."""
    img = Image.new("RGB", (300, 400), (200, 50, 50))
    img.paste((50, 50, 200), (0, 200, 300, 400))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _build_pdf(path: Path, *, rotation: int) -> bytes:
    """Write a two page image-dominant pdf; return the embedded jpeg."""
    jpeg = _two_tone_jpeg()
    doc = pymupdf.open()  # type: ignore[attr-defined]
    for _ in range(PAGE_COUNT):
        page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
        page.insert_image(page.rect, stream=jpeg)
        if rotation:
            page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return jpeg


def _convert(src: Path, config) -> Path:
    with Comicbox(src, config=config) as car:
        car.dump()
    cbz_path = src.with_suffix(".cbz")
    assert cbz_path.is_file(), "conversion produced no cbz"
    return cbz_path


def _page_names(cbz_path: Path) -> list[str]:
    with zipfile.ZipFile(cbz_path) as zf:
        return sorted(n for n in zf.namelist() if not n.lower().endswith(".xml"))


def _page_bytes(cbz_path: Path, name: str) -> bytes:
    with zipfile.ZipFile(cbz_path) as zf:
        return zf.read(name)


def _top_is_blue(data: bytes) -> bool:
    """Report whether the image's top edge is blue (displayed orientation)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    px = img.getpixel((w // 2, h // 20))
    assert isinstance(px, tuple)
    return px[2] > CHANNEL_THRESHOLD and px[0] < CHANNEL_THRESHOLD


@pytest.fixture
def rotated_pdf(tmp_path: Path) -> tuple[Path, bytes]:
    """Two /Rotate 180 pages, stored red side up, displayed blue side up."""
    path = tmp_path / "rotated.pdf"
    return path, _build_pdf(path, rotation=180)


@pytest.fixture
def unrotated_pdf(tmp_path: Path) -> tuple[Path, bytes]:
    """Two unrotated pages, stored and displayed red side up."""
    path = tmp_path / "unrotated.pdf"
    return path, _build_pdf(path, rotation=0)


def test_convert_default_produces_readable_cbz(
    rotated_pdf: tuple[Path, bytes],
) -> None:
    """Default conversion writes real page images, correctly oriented."""
    src, _ = rotated_pdf
    cbz_path = _convert(src, CBZ_CONFIG)

    assert _page_names(cbz_path) == ["0.jpeg", "1.jpeg"]
    with Comicbox(cbz_path) as car:
        assert car.get_page_count() == PAGE_COUNT
    assert _top_is_blue(_page_bytes(cbz_path, "0.jpeg")), (
        "converted page does not match the displayed orientation"
    )
    my_cleanup(TMP_DIR)


def test_convert_image_mode_renders_rotated_pages(
    rotated_pdf: tuple[Path, bytes],
) -> None:
    """Image mode re-renders rotated pages to match the display."""
    src, jpeg = rotated_pdf
    cbz_path = _convert(src, CBZ_IMAGE_CONFIG)

    assert _page_names(cbz_path) == ["0.jpeg", "1.jpeg"]
    data = _page_bytes(cbz_path, "0.jpeg")
    assert data != jpeg, "rotated page written as stored"
    assert _top_is_blue(data), (
        "image-mode page does not match the displayed orientation"
    )
    with Comicbox(cbz_path) as car:
        assert car.get_page_count() == PAGE_COUNT
    my_cleanup(TMP_DIR)


def test_convert_image_mode_preserves_unrotated_originals(
    unrotated_pdf: tuple[Path, bytes],
) -> None:
    """Image mode keeps unrotated embedded images byte-identical."""
    src, jpeg = unrotated_pdf
    cbz_path = _convert(src, CBZ_IMAGE_CONFIG)

    assert _page_names(cbz_path) == ["0.jpeg", "1.jpeg"]
    assert _page_bytes(cbz_path, "0.jpeg") == jpeg, (
        "unrotated embedded image was reencoded"
    )
    my_cleanup(TMP_DIR)
