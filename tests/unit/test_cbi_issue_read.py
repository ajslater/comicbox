"""
ComicBookInfo reads a text issue with the issue parse every format shares.

CBI's issue is an integer, and the reader took the first digits of a text
value: "1.5" and "1a" read as issue 1, "5 1/2" as 5, and "1/2" was dropped.
That is a different issue than the file names, the read-side twin of the
writer fix that leaves out an issue CBI cannot hold.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

CBI_ROOT = "ComicBookInfo/1.0"


def _cbi(issue: Any) -> str:
    return json.dumps({CBI_ROOT: {"series": "Foo", "issue": issue}})


def _read(issue: Any) -> dict:
    with Comicbox() as car:
        car.add_metadata(_cbi(issue), MetadataFormats.COMIC_BOOK_INFO)
        return dict(car.to_dict()["comicbox"])


@pytest.mark.parametrize(
    ("issue", "name", "number", "suffix"),
    [
        ("1/2", "1/2", Decimal("0.5"), None),
        ("½", "½", Decimal("0.5"), None),
        ("5 1/2", "5 1/2", Decimal("5.5"), None),
        ("1.5", "1.5", Decimal("1.5"), None),
        ("1a", "1a", Decimal(1), "a"),
        ("012", "012", Decimal(12), None),
        (1.5, "1.5", Decimal("1.5"), None),
    ],
)
def test_text_issue_uses_the_issue_parse(
    issue: Any, name: str, number: Decimal, suffix: str | None
) -> None:
    """A text or fractional issue is an issue name, split as every format splits it."""
    md_issue = _read(issue)["issue"]
    assert md_issue["name"] == name
    assert md_issue["number"] == number
    assert md_issue.get("suffix") == suffix


@pytest.mark.parametrize("issue", [12, 0, 2.0, "12"], ids=["12", "0", "2.0", "str-12"])
def test_whole_issue_reads_as_before(issue: Any) -> None:
    """A JSON integer, or a whole float or digit string, reads as that integer."""
    md_issue = _read(issue)["issue"]
    assert md_issue["number"] == Decimal(int(float(issue)))
    assert md_issue["name"] == str(int(float(issue)))


def _round_trip(issue: Any) -> dict:
    with Comicbox() as car:
        car.add_metadata(_cbi(issue), MetadataFormats.COMIC_BOOK_INFO)
        return json.loads(car.to_string(MetadataFormats.COMIC_BOOK_INFO))[CBI_ROOT]


@pytest.mark.parametrize("issue", ["1/2", 1.5, "1a"])
def test_non_whole_issue_round_trips_without_issue(issue: Any) -> None:
    """An issue CBI cannot hold is still written without `issue`."""
    cbi = _round_trip(issue)
    assert "issue" not in cbi
    assert cbi["series"] == "Foo"


@pytest.mark.parametrize("issue", [12, 2.0, "012"])
def test_whole_issue_round_trips_as_an_integer(issue: Any) -> None:
    """A whole issue is written back as a JSON integer."""
    assert _round_trip(issue)["issue"] == int(float(issue))
