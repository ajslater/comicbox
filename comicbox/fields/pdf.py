"""PDF Fields."""

from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from comicbox._pdf import PDF_ENABLED
from comicbox.fields.time_fields import DateTimeField

if TYPE_CHECKING:
    from pdffile import PDFFile
else:
    from comicbox._pdf import PDFFile


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    @override
    def _deserialize(
        self,
        value: datetime | str,
        *args: Any,
        **kwargs: Any,
    ) -> datetime | None:
        if PDF_ENABLED and isinstance(value, str):
            with suppress(OSError):
                if pdf_dttm := PDFFile.to_datetime(value):
                    return pdf_dttm
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(
        self,
        value: datetime,
        *args: Any,
        **kwargs: Any,
    ) -> str | float | datetime | None:
        if PDF_ENABLED:
            with suppress(OSError):
                return PDFFile.to_pdf_date(value)
        return super()._serialize(value, *args, **kwargs)
