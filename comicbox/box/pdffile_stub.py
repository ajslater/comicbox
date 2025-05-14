"""A featureless PDFFile stub to help with typing."""

from datetime import datetime, timezone


class PDFFile:
    """Empty."""

    SUFFIX = ""

    @classmethod
    def to_datetime(cls, _value):
        """Zero."""
        return datetime(0, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def to_pdf_date(cls, _value):
        """Empty."""

    @classmethod
    def is_pdffile(cls, _path: str):
        """Stub."""
        return False

    def read(self, filename: str, *, to_pixmap: bool = False) -> bytes:  # noqa: ARG002
        """Empty."""
        return b""

    def namelist(self):
        """Empty."""
        return []

    def infolist(self):
        """Empty."""
        return []

    def close(self):
        """Noop."""

    def get_metadata(self):
        """Empty."""
        return {}

    def save_metadata(self, md):
        """Empty."""
