"""
A half issue is .5 in every issue parse.

comicbox's number and suffix split read "1/2" as number 1, suffix "/2", and
"½" as no number with suffix "½", while CoMet's issue field and reading-list
matching read both as .5. Filenames wrote "½", which read back as number 0
or 5, and any other "/" in an issue was sanitized to "_", which ends the
issue token and invents a title.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.fields import IssueField
from comicbox.readinglists.identity import parse_issue

# issue name -> (number, suffix)
PARSED = (
    ("1/2", Decimal("0.5"), None),
    ("½", Decimal("0.5"), None),
    ("5 1/2", Decimal("5.5"), None),
    ("5½", Decimal("5.5"), None),
    ("1/2 Special", Decimal("0.5"), "Special"),
    ("-1", Decimal(-1), None),
    ("1.5", Decimal("1.5"), None),
    ("1AU", Decimal(1), "AU"),
    ("12", Decimal(12), None),
    ("3/4", Decimal(3), "/4"),
    ("1/2/3", Decimal(1), "/2/3"),
)


def _source(fmt: MetadataFormats, issue: str) -> str:
    if fmt == MetadataFormats.COMIC_INFO:
        return f"<ComicInfo><Series>Foo</Series><Number>{issue}</Number></ComicInfo>"
    if fmt == MetadataFormats.METRON_INFO:
        return (
            "<MetronInfo><Series><Name>Foo</Name></Series>"
            f"<Number>{issue}</Number></MetronInfo>"
        )
    return (
        "comicbox:\n  series:\n    name: Foo\n  issue:\n"
        f"    name: {json.dumps(issue)}\n"
    )


def _read(source: str, fmt: MetadataFormats) -> dict:
    with Comicbox() as car:
        car.add_metadata(source, fmt)
        return dict(car.to_dict()["comicbox"])


@pytest.mark.parametrize(
    "fmt",
    [
        MetadataFormats.COMIC_INFO,
        MetadataFormats.METRON_INFO,
        MetadataFormats.COMICBOX_YAML,
    ],
)
@pytest.mark.parametrize(("issue", "number", "suffix"), PARSED)
def test_issue_parse(
    fmt: MetadataFormats, issue: str, number: Decimal, suffix: str | None
) -> None:
    """The number and suffix agree across formats; the name stays as written."""
    md_issue = _read(_source(fmt, issue), fmt)["issue"]
    assert md_issue["name"] == issue
    assert md_issue.get("number") == number
    assert md_issue.get("suffix") == suffix


@pytest.mark.parametrize(
    ("issue", "name"),
    [
        ("1/2", ".5"),
        ("½", ".5"),
        ("5 1/2", "5.5"),
        ("1/2/3", "1/2/3"),
        ("11/2", "11/2"),
    ],
)
def test_comet_issue_name(issue: str, name: str) -> None:
    """CoMet's issue field spells a half .5, and only a half."""
    xml = f"<comet><title>T</title><series>Foo</series><issue>{issue}</issue></comet>"
    assert _read(xml, MetadataFormats.COMET)["issue"]["name"] == name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("1/2", (".5", "")),
        ("½", (".5", "")),
        ("5 1/2", ("5.5", "")),
        ("000½", ("000.5", "")),
        ("1/2 Special", (".5", " Special")),
        ("3/4", ("3", "/4")),
        ("1/2/3", ("1", "/2/3")),
        ("11/2", ("11", "/2")),
        ("1/23", ("1", "/23")),
    ],
)
def test_split_issue(name: str, expected: tuple[str, str]) -> None:
    """A half in the number position is .5; other fractions are not halves."""
    assert IssueField.split_issue(name) == expected


@pytest.mark.parametrize(
    ("issue", "number", "suffix"),
    [
        ("1/2", Decimal("0.5"), ""),
        ("½", Decimal("0.5"), ""),
        ("5 1/2", Decimal("5.5"), ""),
        ("1/2/3", Decimal(1), "/2/3"),
    ],
)
def test_reading_list_issue_agrees(issue: str, number: Decimal, suffix: str) -> None:
    """Reading-list matching reads an issue as the issue parse does."""
    parsed = parse_issue(issue)
    assert (parsed.number, parsed.suffix) == (number, suffix)


def _filename(issue: str) -> str:
    metadata = {"comicbox": {"series": {"name": "Foo"}, "issue": {"name": issue}}}
    with Comicbox(metadata=metadata) as car:
        return car.to_string(MetadataFormats.FILENAME)


@pytest.mark.parametrize(
    ("issue", "filename", "number", "suffix"),
    [
        ("1/2", "Foo #000½.cbz", Decimal("0.5"), None),
        ("½", "Foo #000½.cbz", Decimal("0.5"), None),
        ("5 1/2", "Foo #005½.cbz", Decimal("5.5"), None),
        ("5½", "Foo #005½.cbz", Decimal("5.5"), None),
        ("3/4", "Foo #003+4.cbz", Decimal(3), "+4"),
        ("1/2/3", "Foo #001+2+3.cbz", Decimal(1), "+2+3"),
        ("-1", "Foo #-001.cbz", Decimal(-1), None),
        ("1.5", "Foo #001.5.cbz", Decimal("1.5"), None),
        ("1AU", "Foo #001AU.cbz", Decimal(1), "AU"),
        ("12", "Foo #012.cbz", Decimal(12), None),
    ],
)
def test_filename_round_trip(
    issue: str, filename: str, number: Decimal, suffix: str | None
) -> None:
    """A half writes as ½ and reads back as itself; no "/" invents a title."""
    assert _filename(issue) == filename
    md = _read(filename, MetadataFormats.FILENAME)
    assert "title" not in md
    assert "stories" not in md
    assert md["issue"]["number"] == number
    assert md["issue"].get("suffix") == suffix


def test_filename_half_with_spaced_suffix() -> None:
    """
    "1/2 Special" keeps its half; its spaced suffix follows the filename rule.

    A suffix after a space leaves the issue token in a filename, as "1 AU"
    does, so it reads back as the title. Before, the title was "2 Special".
    """
    filename = _filename("1/2 Special")
    assert filename == "Foo #000½ Special.cbz"
    md = _read(filename, MetadataFormats.FILENAME)
    assert md["issue"]["number"] == Decimal("0.5")
    assert md["title"] == "Special"
