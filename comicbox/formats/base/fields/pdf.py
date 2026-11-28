"""PDF Fields."""

import sys
from contextlib import suppress
from datetime import datetime
from typing import Any

from comicbox._pdf import get_pdffile
from comicbox.formats.base.fields.time_fields import DateTimeField

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


class PdfDateTimeField(DateTimeField):
    """Datetimefield that serializes to PDF Date Format."""

    @override
    def _deserialize(
        self,
        value: datetime | str,
        *args: Any,
        **kwargs: Any,
    ) -> datetime | None:
        if isinstance(value, str) and (pdffile_cls := get_pdffile()):
            with suppress(OSError):
                if pdf_dttm := pdffile_cls.to_datetime(value):
                    return pdf_dttm
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(
        self,
        value: Any,
        *args: Any,
        **kwargs: Any,
    ) -> str | float | datetime | None:
        if pdffile_cls := get_pdffile():
            with suppress(OSError):
                return pdffile_cls.to_pdf_date(value)
        return super()._serialize(value, *args, **kwargs)
