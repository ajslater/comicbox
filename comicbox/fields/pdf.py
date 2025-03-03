"""PDF Fields."""

from contextlib import suppress

with suppress(ImportError):
    from pdffile import PDFFile

from comicbox.fields.time_fields import DateTimeField


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    def _deserialize(self, value, *args, **kwargs):
        with suppress(NameError, OSError):
            return PDFFile.to_datetime(value)  # type: ignore[reportPossiblyUnboundVariable]
        return super()._deserialize(value, *args, **kwargs)

    def _serialize(self, value, *args, **kwargs):
        with suppress(NameError, OSError):
            return PDFFile.to_pdf_date(value)  # type: ignore[reportPossiblyUnboundVariable]
        return super()._serialize(value, *args, **kwargs)
