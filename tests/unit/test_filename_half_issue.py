"""
A half issue survives the filename round trip.

The filename sanitizer replaced every "/" with "_", so issue "1/2" rendered as
"Foo #001_2.cbz", which reads back with an invented title and story "2".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats


def _filename(metadata: dict) -> str:
    with Comicbox(metadata={"comicbox": metadata}) as car:
        return car.to_string(MetadataFormats.FILENAME)


def _read_filename(filename: str) -> dict:
    with Comicbox() as car:
        car.add_metadata(filename, MetadataFormats.FILENAME)
        return dict(car.to_dict()["comicbox"])


@pytest.mark.parametrize(
    ("issue", "number"), [("1/2", Decimal("0.5")), ("5 1/2", Decimal("5.5"))]
)
def test_half_issue_round_trips_without_a_title(issue: str, number: Decimal) -> None:
    """The half stays in the issue token and invents no title or story."""
    filename = _filename({"series": {"name": "Foo"}, "issue": {"name": issue}})
    assert "/" not in filename
    assert "_" not in filename
    md = _read_filename(filename)
    assert "title" not in md
    assert "stories" not in md
    assert md["issue"]["number"] == number
    assert "suffix" not in md["issue"]


def test_slash_in_series_still_sanitizes() -> None:
    """The half rewrite applies to the issue only."""
    filename = _filename({"series": {"name": "Foo/Bar 1/2"}, "issue": {"name": "3"}})
    assert filename.startswith("Foo_Bar 1_2 #003")
