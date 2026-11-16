"""
A string that holds only part of a date never becomes a date (B5).

dateutil fills a missing part from today, so CoMet's ``<date>2006-07</date>``
read on the 14th was the 14th of July. The parts a string holds are kept as
the comic's year and month, and the rest is absent.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.time_fields import DateParts, date_parts

_COMET = (
    '<?xml version="1.0"?><comet xmlns:comet="http://www.denvog.com/comet/">'
    "<series>Civil War</series><issue>1</issue><date>{}</date></comet>"
)
_METRON = (
    '<?xml version="1.0"?><MetronInfo><Series><Name>Civil War</Name></Series>'
    "<Number>1</Number><CoverDate>{}</CoverDate></MetronInfo>"
)
_YAML = "comicbox:\n  series: {{name: Civil War}}\n  date:\n    cover_date: '{}'\n"
_FORMATS = (
    (MetadataFormats.COMET, _COMET),
    (MetadataFormats.METRON_INFO, _METRON),
    (MetadataFormats.COMICBOX_YAML, _YAML),
)


def _date(fmt: MetadataFormats, text: str) -> dict[str, Any]:
    with Comicbox(metadata=text, fmt=fmt) as box:
        return dict((box.to_dict().get("comicbox") or {}).get("date") or {})


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("2006", DateParts(2006, None, None)),
        ("2006-07", DateParts(2006, 7, None)),
        ("July 2006", DateParts(2006, 7, None)),
        ("2006-07-04", DateParts(2006, 7, 4)),
        ("not a date", None),
    ],
)
def test_date_parts_fills_in_nothing(text: str, parts: DateParts | None) -> None:
    assert date_parts(text) == parts


@pytest.mark.parametrize(("fmt", "template"), _FORMATS, ids=lambda x: str(x)[:20])
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2006", {"year": 2006}),
        ("2006-07", {"year": 2006, "month": 7}),
        ("July 2006", {"year": 2006, "month": 7}),
    ],
)
def test_a_partial_cover_date_is_kept_as_its_parts(
    fmt: MetadataFormats, template: str, text: str, expected: dict[str, int]
) -> None:
    assert _date(fmt, template.format(text)) == expected


@pytest.mark.parametrize(("fmt", "template"), _FORMATS, ids=lambda x: str(x)[:20])
@pytest.mark.parametrize("text", ["2006-07-04", "July 4, 2006", "2006-07-04T10:00:00"])
def test_a_whole_date_is_still_a_date(
    fmt: MetadataFormats, template: str, text: str
) -> None:
    assert _date(fmt, template.format(text)) == {
        "cover_date": date(2006, 7, 4),
        "year": 2006,
        "month": 7,
        "day": 4,
    }


def test_a_partial_store_date_is_dropped() -> None:
    """The model has no parts for a store date, so it is absent."""
    text = _YAML.format("2006-07-04") + "    store_date: '2006-07'\n"
    assert "store_date" not in _date(MetadataFormats.COMICBOX_YAML, text)


def test_a_source_year_beats_the_partial_dates_year() -> None:
    text = _YAML.format("2006-07") + "    year: 2007\n"
    assert _date(MetadataFormats.COMICBOX_YAML, text) == {"year": 2007, "month": 7}
