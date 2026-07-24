"""Test magic byte format detection."""

import pytest

from comicbox.box.archive.sniff import sniff_ext

SNIFF_CASES = (
    (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3", "pdf"),
    (b"\xff\xd8\xff\xe0\x00\x10JFIF", "jpeg"),
    (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "png"),
    (b"GIF89a\x01\x00", "gif"),
    (b"II*\x00\x08\x00\x00\x00", "tiff"),
    (b"RIFF\x24\x00\x00\x00WEBPVP8 ", "webp"),
    (b"P6\n800 1200\n255\n", "ppm"),
    (b"P4 1 1\n", "pbm"),
    # Not netpbm: no whitespace after the magic number.
    (b"P6x\n", ""),
    (b"Poorly formed data", ""),
    (b"", ""),
)


@pytest.mark.parametrize(("data", "ext"), SNIFF_CASES)
def test_sniff_ext(data: bytes, ext: str) -> None:
    """Test detecting extensions from leading bytes."""
    assert sniff_ext(data) == ext
