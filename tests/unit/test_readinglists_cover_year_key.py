"""
The weakest identity key: series, issue and cover year (R3-D).

An entry with no id and no start year or volume, as a CBL row with ``Year``
and no ``Volume`` is, used to match nothing, not even its own copy.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import (
    ENTRIES_KEY,
    Verdict,
    combine,
    compare,
    entry_keys,
    loads,
)
from comicbox.readinglists.match import FoundBy, match_comics, plan_arcs

_CBL = """<?xml version="1.0" encoding="utf-8"?>
<ReadingList xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Name>Batman: Year One</Name>
  <Books>
    <Book Series="Batman" Number="404" Year="1987" />
    <Book Series="Batman" Number="405" Year="1987" />
    <Book Series="Batman" Number="406" Year="1987" />
  </Books>
</ReadingList>
"""


def _entry(
    number: str = "1",
    *,
    start_year: int | None = None,
    volume: int | None = None,
    year: int | None = None,
    cover: date | None = None,
    **ids: str,
) -> dict[str, Any]:
    series: dict[str, Any] = {"name": "Batman"}
    if start_year is not None:
        series["start_year"] = start_year
    entry: dict[str, Any] = {"series": series, "issue": {"name": number}}
    if volume is not None:
        entry["volume"] = {"number": volume}
    when: dict[str, Any] = {}
    if year is not None:
        when["year"] = year
    if cover is not None:
        when["cover_date"] = cover
    if when:
        entry["date"] = when
    if ids:
        entry["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return entry


def _list(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"name": "Batman", "ordered": True, ENTRIES_KEY: list(entries)}


# ------------------------------------------------------------ entry_keys


@pytest.mark.parametrize(
    ("entry", "keys"),
    [
        (_entry(year=2016), (("name-year", "batman", 2016, Decimal(1), ""),)),
        (
            _entry(cover=date(2016, 8, 1)),
            (("name-year", "batman", 2016, Decimal(1), ""),),
        ),
        # date.year is the cover year when both are given.
        (
            _entry(year=2017, cover=date(2016, 8, 1)),
            (("name-year", "batman", 2017, Decimal(1), ""),),
        ),
        # Every entry with a cover year gets it, after its stronger keys.
        (
            _entry(start_year=2016, year=2016, comicvine="9"),
            (
                ("id", "comicvine", "9"),
                ("name", "batman", 2016, Decimal(1), ""),
                ("name-year", "batman", 2016, Decimal(1), ""),
            ),
        ),
        # No id, no start year or volume and no cover year: still no key.
        (_entry(), ()),
    ],
)
def test_entry_keys_with_a_cover_year(
    entry: dict[str, Any], keys: tuple[Any, ...]
) -> None:
    assert entry_keys(entry) == keys


# ------------------------------------------------------ combine, compare


def test_a_cbl_with_years_and_no_volumes_is_the_same_as_itself() -> None:
    """Each row matched nothing, so combining doubled it and compare differed."""
    reading_list = loads(_CBL).reading_list

    assert compare(reading_list, reading_list).verdict is Verdict.SAME
    result = combine([reading_list, reading_list])
    assert result.reading_list == reading_list


def test_a_cover_year_row_joins_a_start_year_row_and_is_reported() -> None:
    year_only = _list(_entry(year=2016))
    start_year = _list(_entry(start_year=2016, cover=date(2016, 8, 1)))

    result = combine([year_only, start_year])

    (joined,) = result.reading_list[ENTRIES_KEY]
    assert joined["series"]["start_year"] == 2016
    assert result.name_joins == (0,)
    assert compare(year_only, start_year).verdict is Verdict.SAME


def test_two_volumes_with_one_number_and_two_cover_years_do_not_join() -> None:
    result = combine([_list(_entry(year=2011)), _list(_entry(year=2016))])
    assert [entry["date"]["year"] for entry in result.reading_list[ENTRIES_KEY]] == [
        2011,
        2016,
    ]


def test_a_cover_year_link_never_takes_a_row_a_name_link_wanted() -> None:
    """
    The weakest key is applied last.

    The second input holds a year-only row and a start-year row of one
    issue; the first input's row has both keys. Joined in row order it took
    the year-only row, and left the start-year row, its truer match, alone.
    """
    both = _list(_entry(start_year=2016, year=2016))
    second = _list(_entry(year=2016), _entry(start_year=2016))

    result = combine([both, second])

    sources = [
        [(origin.input_index, origin.row) for origin in origins]
        for origins in result.provenance
    ]
    assert [(0, 0), (1, 1)] in sources
    assert [(1, 0)] in sources


# ----------------------------------------- two volumes, one cover year


def _groups(*inputs: dict[str, Any]) -> list[set[int]]:
    """Combine one-row lists; list the inputs each combined entry came from."""
    result = combine(list(inputs))
    return [{origin.input_index for origin in origins} for origins in result.provenance]


_V2011 = _entry(start_year=2011, cover=date(2016, 8, 1))
_V2016 = _entry(start_year=2016, cover=date(2016, 8, 1))
_YEAR_ONLY = _entry(year=2016)


def test_two_volumes_with_one_cover_year_stay_apart() -> None:
    """Avengers #1 of 2011 and of 2016, both dated 2016, joined as one."""
    assert _groups(_list(_V2011), _list(_V2016)) == [{0}, {1}]
    assert compare(_list(_V2011), _list(_V2016)).verdict is not Verdict.SAME


@pytest.mark.parametrize(
    "order",
    [(0, 1, 2), (0, 2, 1), (2, 0, 1), (2, 1, 0)],
)
def test_two_volumes_never_meet_through_a_cover_year_row(
    order: tuple[int, ...],
) -> None:
    """Refused on the group, not the pair: each joins the year-only row."""
    rows = (_V2011, _V2016, _YEAR_ONLY)
    inputs = [_list(rows[index]) for index in order]
    position = {row: order.index(row) for row in range(3)}

    groups = _groups(*inputs)

    assert len(groups) == 2
    assert not any({position[0], position[1]} <= group for group in groups)
    assert any(position[2] in group and len(group) == 2 for group in groups)


def test_an_id_still_joins_rows_whose_series_years_differ() -> None:
    """Only a cover-year link is held to one series year; an id is evidence."""
    one = _entry(start_year=2011, year=2016, comicvine="7")
    other = _entry(start_year=2016, year=2016, comicvine="7")
    assert _groups(_list(one), _list(other)) == [{0, 1}]


@pytest.mark.parametrize("volume", [_V2011, _V2016])
def test_a_row_with_no_start_year_joins_either_volume(volume: dict[str, Any]) -> None:
    assert _groups(_list(_YEAR_ONLY), _list(volume)) == [{0, 1}]


@pytest.mark.parametrize(
    ("row", "joins"),
    [
        # Volume 2 is not a year, so it cannot be compared with one.
        (_entry(volume=2, year=2016), True),
        # Volume 2011 is a year, as a CBL's Volume is: another volume.
        (_entry(volume=2011, year=2016), False),
        (_entry(volume=2016, year=2016), True),
    ],
)
def test_a_volume_number_is_a_year_from_1900(row: dict[str, Any], joins: bool) -> None:
    groups = _groups(_list(row), _list(_V2016))
    assert (groups == [{0, 1}]) is joins


# ----------------------------------------------------------------- match


def _tags(**fields: Any) -> dict[str, Any]:
    entry = _entry(**fields)
    if "date" in entry and "cover_date" in entry["date"]:
        entry["date"] = {"cover_date": entry["date"]["cover_date"]}
    return entry


def test_match_finds_a_comic_by_series_issue_and_cover_year() -> None:
    comics = {Path("batman.cbz"): _tags(cover=date(2016, 8, 1))}

    (found,) = match_comics(_list(_entry(year=2016)), comics).found

    (comic,) = found.comics
    assert comic.by is FoundBy.NAME_YEAR
    assert comic.by.strict


def test_a_stronger_key_names_how_the_comic_was_found() -> None:
    comics = {Path("batman.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1))}
    entry = _entry(start_year=2016, year=2016)
    (found,) = match_comics(_list(entry), comics).found
    assert found.comics[0].by is FoundBy.NAME


def test_a_cover_year_match_never_finds_another_volume() -> None:
    comics = {
        Path("v2011.cbz"): _tags(start_year=2011, cover=date(2016, 8, 1)),
        Path("v2016.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1)),
    }
    entry = _entry(start_year=2011, year=2016)

    (found,) = match_comics(_list(entry), comics).found

    assert found.paths == (Path("v2011.cbz"),)


def test_an_entry_that_fits_two_volumes_is_ambiguous() -> None:
    """Avengers #1 dated 2016, no start year: the 2011 and 2016 volumes alike."""
    comics = {
        Path("v2011.cbz"): _tags(start_year=2011, cover=date(2016, 8, 1)),
        Path("v2016.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1)),
    }
    reading_list = _list(_entry(year=2016))

    result = match_comics(reading_list, comics)

    (found,) = result.found
    assert found.paths == (Path("v2011.cbz"), Path("v2016.cbz"))
    assert found.volumes == (2011, 2016)
    assert found.ambiguous
    assert plan_arcs(reading_list, comics, result, "Avengers") == ()


def test_an_entry_found_by_a_stronger_key_is_not_ambiguous() -> None:
    """Only an entry found by its cover year alone is: its id names the issue."""
    comics = {
        Path("v2011.cbz"): _tags(start_year=2011, cover=date(2016, 8, 1)),
        Path("v2016.cbz"): _tags(
            start_year=2016, cover=date(2016, 8, 1), comicvine="7"
        ),
    }
    reading_list = _list(_entry(year=2016, comicvine="7"))

    result = match_comics(reading_list, comics)

    (found,) = result.found
    assert not found.ambiguous
    changes = plan_arcs(reading_list, comics, result, "Avengers")
    assert Path("v2016.cbz") in [change.path for change in changes]


@pytest.mark.parametrize(
    "comics",
    [
        # Copies of one volume.
        {
            Path("a/v2016.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1)),
            Path("b/v2016.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1)),
        },
        # A comic with no series year beside comics of one volume.
        {
            Path("v2016.cbz"): _tags(start_year=2016, cover=date(2016, 8, 1)),
            Path("year-only.cbz"): _tags(cover=date(2016, 8, 1)),
        },
    ],
)
def test_comics_of_one_volume_are_not_ambiguous(comics: dict[Path, Any]) -> None:
    reading_list = _list(_entry(year=2016))

    result = match_comics(reading_list, comics)

    (found,) = result.found
    assert not found.ambiguous
    changes = plan_arcs(reading_list, comics, result, "Avengers")
    assert [change.path for change in changes] == sorted(comics)


def test_the_vetoes_apply_to_a_cover_year_match() -> None:
    comics = {Path("batman.cbz"): _tags(cover=date(2016, 8, 1), metron="2")}
    entry = _entry(year=2016, metron="1")
    assert match_comics(_list(entry), comics).found == ()
