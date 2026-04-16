"""PDF Fields."""

from contextlib import suppress
from datetime import datetime
from typing import Any

from typing_extensions import override

from comicbox.fields.time_fields import DateTimeField

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.pdffile_stub import PDFFile


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    @override
    def _deserialize(
        self,
        value: datetime | str,
        *args: Any,
        **kwargs: Any,
    ) -> datetime | None:
        with suppress(NameError, OSError):
            if isinstance(value, str) and (pdf_dttm := PDFFile.to_datetime(value)):
                return pdf_dttm
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(
        self,
        value: datetime,
        *args: Any,
        **kwargs: Any,
    ) -> str | float | datetime | None:
        with suppress(NameError, OSError):
            return PDFFile.to_pdf_date(value)
        return super()._serialize(value, *args, **kwargs)
