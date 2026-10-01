"""
PDF dates read whatever optional fields they carry, always timezone-aware.

A PDF date is `D:YYYY[MM[DD[HH[mm[SS[O[HH['mm']]]]]]]]`. Before comicbox-pdffile
1.0.0 its parser demanded the `'mm'` timezone minutes, so a date without a
timezone (or a `Z`, or a bare year) failed there and again in comicbox's
fallback parser, and the metadata field was silently dropped.
`PdfDateTimeField` returns pdffile's datetime directly, skipping the base
field's UTC fill, so pdffile must also hand back an aware datetime.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.pdf import PdfDateTimeField

_DTTM = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("pdf_date", "expected"),
    [
        ("D:20250102030405", _DTTM),
        ("D:20250102030405Z", _DTTM),
        ("D:2025", datetime(2025, 1, 1, tzinfo=UTC)),
        (
            "D:20250102030405-0800",
            _DTTM.replace(tzinfo=timezone(timedelta(hours=-8))),
        ),
        (
            "D:20250102030405+05'00'",
            _DTTM.replace(tzinfo=timezone(timedelta(hours=5))),
        ),
    ],
)
def test_pdf_date_field_deserializes_aware(pdf_date: str, expected: datetime):
    """Every PDF date form parses, and tz-less ones come back as UTC."""
    dttm = PdfDateTimeField().deserialize(pdf_date)
    assert dttm == expected
    assert dttm.tzinfo == expected.tzinfo


def test_pdf_moddate_without_timezone_reads_as_updated_at():
    """A tz-less ModDate surfaces as a UTC updated_at instead of vanishing."""
    md = {"MuPDF": {"modDate": "D:20250102030405", "title": "T"}}
    with Comicbox(metadata=md, fmt=MetadataFormats.PDF) as car:
        updated_at = car.to_dict()["comicbox"]["updated_at"]
    assert updated_at == _DTTM
    assert updated_at.tzinfo == UTC
