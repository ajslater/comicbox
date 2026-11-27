"""
ComicBookInfo writes an issue only when it is a whole number.

CBI's issue is an integer. The writer read the free-text issue name through
IntegerField, which takes the first digits, so "1.5" and "1a" were written
as issue 1: a different issue, not a value left out.
"""

from __future__ import annotations

import json

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

CBI_ROOT = "ComicBookInfo/1.0"


def _write_cbi(number: str) -> dict:
    xml = f"<ComicInfo><Series>Foo</Series><Number>{number}</Number></ComicInfo>"
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.COMIC_INFO)
        written = car.to_string(MetadataFormats.COMIC_BOOK_INFO)
    return json.loads(written)[CBI_ROOT]


@pytest.mark.parametrize("number", ["1.5", "1a", "-1", "½"])
def test_non_integer_issue_is_not_written(number: str) -> None:
    """An issue CBI cannot represent is left out."""
    cbi = _write_cbi(number)
    assert "issue" not in cbi
    assert cbi["series"] == "Foo"


@pytest.mark.parametrize("number", ["1", "001", "12"])
def test_integer_issue_is_written(number: str) -> None:
    """A whole issue number is written as an integer."""
    assert _write_cbi(number)["issue"] == int(number)


def test_cbi_issue_still_reads() -> None:
    """The liberal read is unchanged."""
    cbi = json.dumps({CBI_ROOT: {"series": "Foo", "issue": "12"}})
    with Comicbox() as car:
        car.add_metadata(cbi, MetadataFormats.COMIC_BOOK_INFO)
        md = car.to_dict()["comicbox"]
    assert md["issue"]["name"] == "12"
