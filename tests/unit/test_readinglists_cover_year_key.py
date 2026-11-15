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
from comicbox.readinglists.match import FoundBy, match_comics

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
    year: int | None = None,
    cover: date | None = None,
    **ids: str,
) -> dict[str, Any]:
    series: dict[str, Any] = {"name": "Batman"}
    if start_year is not None:
        series["start_year"] = start_year
    entry: dict[str, Any] = {"series": series, "issue": {"name": number}}
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


def test_the_vetoes_apply_to_a_cover_year_match() -> None:
    comics = {Path("batman.cbz"): _tags(cover=date(2016, 8, 1), metron="2")}
    entry = _entry(year=2016, metron="1")
    assert match_comics(_list(entry), comics).found == ()
