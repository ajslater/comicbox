"""Identify file formats by their leading magic bytes."""

from types import MappingProxyType
from typing import Final

# Only signatures that cannot be confused with another format belong here.
# The result names files on disk, so a wrong guess mislabels the data.
_MAGIC_EXTS: Final[tuple[tuple[bytes, str], ...]] = (
    (b"%PDF-", "pdf"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "jpx"),
    (b"\xffO\xffQ", "jpx"),
)
# A netpbm magic number is only a header when whitespace follows it, so these
# two byte prefixes need a stricter test than the table above.
_PNM_EXTS: Final = MappingProxyType(
    {
        b"1": "pbm",
        b"2": "pgm",
        b"3": "ppm",
        b"4": "pbm",
        b"5": "pgm",
        b"6": "ppm",
        b"7": "pam",
    }
)


def _sniff_pnm(data: bytes) -> str:
    if data[:1] != b"P" or not data[2:3].isspace():
        return ""
    return _PNM_EXTS.get(data[1:2], "")


def _sniff_webp(data: bytes) -> str:
    return "webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else ""


def sniff_ext(data: bytes) -> str:
    """Return the file extension for data, or empty if unrecognized."""
    for magic, ext in _MAGIC_EXTS:
        if data.startswith(magic):
            return ext
    return _sniff_webp(data) or _sniff_pnm(data)
