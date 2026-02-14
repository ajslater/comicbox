"""A featureless PDFFile stub to help with typing."""

from datetime import datetime, timezone
from io import BytesIO


class PDFFile:
    """Empty."""

    SUFFIX = ""

    @classmethod
    def to_datetime(cls, _value) -> datetime:
        """Zero."""
        return datetime(0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def to_pdf_date(cls, _value):
        """Empty."""

    @classmethod
    def is_pdffile(cls, _path: str) -> bool:
        """Stub."""
        return False

    def save(self):
        """Empty."""

    def read(self, filename: str, *, to_pixmap: bool = False) -> bytes:  # noqa: ARG002
        """Empty."""
        return b""

    def namelist(self) -> list:
        """Empty."""
        return []

    def infolist(self) -> list:
        """Empty."""
        return []

    def close(self):
        """Noop."""

    def get_metadata(self) -> dict:
        """Empty."""
        return {}

    def write_metadata(self, md):
        """Empty."""

    def writestr(self, name: str, buffer: str | bytes | bytearray | BytesIO, **_kwargs):
        """Empty."""

    def remove(self, name):
        """Empty."""

    def repack(self):
        """Empty."""
