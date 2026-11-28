"""
ComicInfo's -1 means unset.

ComicInfo.xsd defaults Count, AlternateCount, Volume, Year, Month and Day to
-1, its "unset" value. IntegerField read only digits, so "-1" was 1: a file
carrying the defaults loaded as volume 1, issue count 1 and cover date
0001-01-01, and every format written from it carried them.
"""

from __future__ import annotations

from typing import Any

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.formats.comic_info.schema import ComicInfoSchema

UNSET_XML = (
    "<ComicInfo><Series>Foo</Series><Number>1</Number>"
    "<Count>-1</Count><Volume>-1</Volume>"
    "<AlternateSeries>Bar</AlternateSeries><AlternateCount>-1</AlternateCount>"
    "<Year>-1</Year><Month>-1</Month><Day>-1</Day></ComicInfo>"
)


def _read(xml: str) -> dict:
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        return dict(car.to_dict()["comicbox"])


def test_unset_sentinel_loads_as_nothing() -> None:
    """None of the six -1 defaults becomes data."""
    md = _read(UNSET_XML)
    assert "date" not in md
    assert "issue_count" not in md.get("series", {})
    assert "number" not in md.get("volume", {})
    assert "issue_count" not in md.get("volume", {})
    assert md["series"]["name"] == "Foo"
    assert md["issue"]["name"] == "1"


def test_schema_drops_each_sentinel() -> None:
    """The schema itself reads all six -1 tags as absent, AlternateCount too."""
    loaded: dict[str, Any] = ComicInfoSchema().loads(UNSET_XML)  # pyright: ignore[reportAssignmentType]
    for tag in ("Count", "Volume", "AlternateCount", "Year", "Month", "Day"):
        assert tag not in loaded["ComicInfo"]


def test_real_values_still_load() -> None:
    """Positive values are untouched by the sentinel."""
    md = _read(
        "<ComicInfo><Series>Foo</Series><Count>12</Count><Volume>2</Volume>"
        "<Year>1999</Year><Month>3</Month><Day>4</Day></ComicInfo>"
    )
    assert md["date"]["cover_date"].isoformat() == "1999-03-04"
    assert md["volume"]["number"] == 2
    assert md["volume"]["issue_count"] == 12


def test_parse_str_keeps_a_leading_minus() -> None:
    """A minus that starts the number is its sign."""
    assert IntegerField.parse_str("-1") == -1
    assert IntegerField.parse_str(" -12 ") == -12


def test_parse_str_first_number_unchanged() -> None:
    """A dash between or after letters and digits is not a sign."""
    assert IntegerField.parse_str("v2") == 2
    assert IntegerField.parse_str("1-3") == 1
    assert IntegerField.parse_str("Vol-2") == 2
    assert IntegerField.parse_str("12") == 12
