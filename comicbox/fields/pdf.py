"""PDF Fields."""

from contextlib import suppress

from typing_extensions import override

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.pdffile_stub import PDFFile

from comicbox.fields.time_fields import DateTimeField


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    @override
    def _deserialize(self, value, *args, **kwargs):
        with suppress(NameError, OSError):
            return PDFFile.to_datetime(value)
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(self, value, *args, **kwargs):
        with suppress(NameError, OSError):
            return PDFFile.to_pdf_date(value)
        return super()._serialize(value, *args, **kwargs)
