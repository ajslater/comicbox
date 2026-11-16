"""
A date is one fact across sources (D3, section 10).

``-m "{date: {cover_date: 2006-07}}"`` on a comic dated 1950-11-01 came back
1950-11-01 when the comic's date was a CoMet or MetronInfo cover date, and
2006-07-01, the old day under the new month, from ComicInfo's parts; a whole
``-m`` date lost to ComicInfo's parts. A higher source's date that
contradicts the one below now replaces it whole; one that agrees keeps the
parts only the lower one knows.
"""

from __future__ import annotations

import json
import zipfile
from argparse import Namespace
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.config import get_config

if TYPE_CHECKING:
    from pathlib import Path

_TAGS = {
    "CoMet": (
        "CoMet.xml",
        (
            '<?xml version="1.0"?><comet xmlns="http://www.denvog.com/comet/">'
            "<title>T</title><series>S</series><date>1950-11-01</date></comet>"
        ),
    ),
    "MetronInfo": (
        "MetronInfo.xml",
        (
            '<?xml version="1.0"?><MetronInfo><Series><Name>S</Name></Series>'
            "<CoverDate>1950-11-01</CoverDate></MetronInfo>"
        ),
    ),
    "ComicInfo": (
        "ComicInfo.xml",
        (
            '<?xml version="1.0"?><ComicInfo><Series>S</Series>'
            "<Year>1950</Year><Month>11</Month><Day>1</Day></ComicInfo>"
        ),
    ),
}
_WHOLE = {"cover_date": date(2006, 7, 15), "year": 2006, "month": 7, "day": 15}


def _comic(path: Path, *members: tuple[str, str], comment: str = "") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("p0.jpg", b"x")
        for name, data in members:
            archive.writestr(name, data)
        archive.comment = comment.encode()
    return path


def _date(path: Path, patch: str | None = None) -> dict[str, Any]:
    dests = {"general.metadata_cli": [patch]} if patch else {}
    config = get_config(Namespace(comicbox=Namespace(**dests)))
    with Comicbox(path, config=config) as box:
        return dict(box.to_dict()["comicbox"].get("date") or {})


@pytest.mark.parametrize("fmt", list(_TAGS))
@pytest.mark.parametrize(
    ("cover_date", "expected"),
    [
        ("2006-07", {"year": 2006, "month": 7}),
        ("'2006'", {"year": 2006}),
        ("2006-07-15", _WHOLE),
    ],
    ids=["year and month", "year", "whole"],
)
def test_a_higher_date_that_contradicts_replaces_it_whole(
    tmp_path: Path, fmt: str, cover_date: str, expected: dict[str, Any]
) -> None:
    path = _comic(tmp_path / "comic.cbz", _TAGS[fmt])

    assert _date(path, f"{{date: {{cover_date: {cover_date}}}}}") == expected


def test_a_lower_partial_date_leaves_a_whole_one_above_it(tmp_path: Path) -> None:
    """ComicInfo's 2006-07 is below MetronInfo's 1950-11-01."""
    path = _comic(
        tmp_path / "comic.cbz",
        ("ComicInfo.xml", "<ComicInfo><Year>2006</Year><Month>7</Month></ComicInfo>"),
        _TAGS["MetronInfo"],
    )

    assert _date(path) == {
        "cover_date": date(1950, 11, 1),
        "year": 1950,
        "month": 11,
        "day": 1,
    }


def test_an_agreeing_date_keeps_the_day_only_the_lower_one_knows(
    tmp_path: Path,
) -> None:
    """ComicBookInfo has no day; ComicInfo's 15th is kept beside its 2006-07."""
    path = _comic(
        tmp_path / "comic.cbz",
        (
            "ComicInfo.xml",
            "<ComicInfo><Series>S</Series><Year>2006</Year><Month>7</Month><Day>15</Day></ComicInfo>",
        ),
        comment=json.dumps(
            {
                "ComicBookInfo/1.0": {
                    "series": "S",
                    "publicationYear": 2006,
                    "publicationMonth": 7,
                }
            }
        ),
    )

    assert _date(path) == _WHOLE
    assert _date(path, "{date: {cover_date: 2006-07}}") == _WHOLE
