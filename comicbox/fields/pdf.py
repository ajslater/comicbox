"""PDF Fields."""

from contextlib import suppress
from datetime import datetime

from typing_extensions import override

from comicbox.fields.time_fields import DateTimeField

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.pdffile_stub import PDFFile


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    @override
    def _deserialize(self, value, *args, **kwargs) -> datetime | None:
        with suppress(NameError, OSError):
            if pdf_dttm := PDFFile.to_datetime(value):
                return pdf_dttm
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(self, value, *args, **kwargs):
        with suppress(NameError, OSError):
            return PDFFile.to_pdf_date(value)
        return super()._serialize(value, *args, **kwargs)
