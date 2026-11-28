"""
Loose matches that differ by id, and repeated loose rows in combine.

A: two loose comics whose ids from one database differ are two issues, so
they are ambiguous, listed and never tagged, as two volumes are. B: a loose
row's conflicting-candidates check in ``combine`` counts every row of the
other list, whatever its occurrence.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from comicbox.readinglists import ENTRIES_KEY, combine
from comicbox.readinglists.match import FoundBy, match_comics, plan_arcs
from comicbox.readinglists.render import print_ambiguous

_COVER = date(2016, 8, 1)


def _row(
    *,
    start_year: int | None = None,
    volume: int | None = None,
    cover: date | None = _COVER,
    **ids: str,
) -> dict[str, Any]:
    series: dict[str, Any] = {"name": "Ardent"}
    if start_year is not None:
        series["start_year"] = start_year
    row: dict[str, Any] = {"series": series, "issue": {"name": "1"}}
    if volume is not None:
        row["volume"] = {"number": volume}
    if cover is not None:
        row["date"] = {"cover_date": cover}
    if ids:
        row["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return row


def _identified(ids: dict[str, str]) -> dict[str, Any]:
    """Build a bare row with these ids."""
    row = _row()
    if ids:
        row["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return row


def _entry(**fields: Any) -> dict[str, Any]:
    """Build an entry dated by its year, as a CBL row with ``Year`` is."""
    entry = _row(**fields, cover=None)
    entry["date"] = {"year": _COVER.year}
    return entry


def _list(*entries: dict[str, Any], ordered: bool = True) -> dict[str, Any]:
    return {"name": "Ardent", "ordered": ordered, ENTRIES_KEY: list(entries)}


def _found(entry: dict[str, Any], comics: dict[Path, Any]) -> dict[str, Any]:
    """Match one entry; name each comic found, how, and whether ambiguous."""
    reading_list = _list(entry)
    result = match_comics(reading_list, comics)
    planned = {
        change.path.stem for change in plan_arcs(reading_list, comics, result, "A")
    }
    if not result.found:
        return {"found": {}, "planned": planned}
    (found,) = result.found
    return {
        "found": {
            comic.path.stem: (comic.by, comic.ambiguous) for comic in found.comics
        },
        "planned": planned,
        "ids": found.ids,
        "volumes": found.volumes,
    }


# ------------------------------------------------------------------ A: match


def test_two_loose_comics_with_differing_ids_are_ambiguous() -> None:
    """The fuzzer's case A: both were found and tagged."""
    comics = {Path("a.cbz"): _row(metron="101"), Path("b.cbz"): _row(metron="107")}

    got = _found(_entry(), comics)

    assert got["found"] == {
        "a": (FoundBy.NAME_YEAR, True),
        "b": (FoundBy.NAME_YEAR, True),
    }
    assert got["planned"] == set()
    assert got["ids"] == (("metron", "101"), ("metron", "107"))
    assert got["volumes"] == ()


def test_loose_comics_with_differing_ids_on_the_volume_key_are_ambiguous() -> None:
    """The volume key is loose too: Ardent volume 1 #1, twice, by two ids."""
    comics = {
        Path("a.cbz"): _row(volume=1, metron="101"),
        Path("b.cbz"): _row(volume=1, metron="107"),
    }

    got = _found(_entry(volume=1), comics)

    assert got["found"] == {"a": (FoundBy.NAME, True), "b": (FoundBy.NAME, True)}
    assert got["planned"] == set()


@pytest.mark.parametrize(
    ("ids_a", "ids_b"),
    [
        # Two databases: nothing to compare.
        ({"metron": "101"}, {"comicvine": "55"}),
        # One id beside none.
        ({"metron": "101"}, {}),
        # One id, shared.
        ({"metron": "101"}, {"metron": "101"}),
        # A barcode names a cover or a printing, never another issue.
        ({"upc": "75960608936800111"}, {"upc": "75960608936800121"}),
    ],
)
def test_loose_comics_whose_ids_do_not_differ_are_found(
    ids_a: dict[str, str], ids_b: dict[str, str]
) -> None:
    comics = {Path("a.cbz"): _identified(ids_a), Path("b.cbz"): _identified(ids_b)}

    got = _found(_entry(), comics)

    assert got["found"] == {
        "a": (FoundBy.NAME_YEAR, False),
        "b": (FoundBy.NAME_YEAR, False),
    }
    assert got["planned"] == {"a", "b"}


def test_two_comics_sharing_an_id_beside_one_that_differs_are_all_ambiguous() -> None:
    comics = {
        Path("a.cbz"): _row(metron="101"),
        Path("b.cbz"): _row(metron="101"),
        Path("c.cbz"): _row(metron="107"),
    }

    got = _found(_entry(), comics)

    assert {stem for stem, (_, ambiguous) in got["found"].items() if ambiguous} == {
        "a",
        "b",
        "c",
    }
    assert got["planned"] == set()


def test_a_comic_with_no_id_beside_two_that_differ_is_ambiguous() -> None:
    """
    The identity case: the entry made from the bare comic's own tags.

    Nothing on it tells which of the two issues it is, as nothing on an
    entry with no start year tells the 2011 and 2016 volumes apart.
    """
    bare = _row()
    comics = {
        Path("a.cbz"): bare,
        Path("b.cbz"): _row(metron="101"),
        Path("c.cbz"): _row(metron="107"),
    }

    got = _found(bare, comics)

    assert all(ambiguous for _, ambiguous in got["found"].values())
    assert set(got["found"]) == {"a", "b", "c"}


def test_a_loose_comic_whose_id_differs_from_a_strong_match_is_refused() -> None:
    """
    The id analogue of a loose comic of another volume than a strong match.

    The entry's Comic Vine id finds a; b shares only the cover year and has
    another Metron id than a, so it is another issue than the one found.
    """
    comics = {
        Path("a.cbz"): _row(comicvine="7", metron="101"),
        Path("b.cbz"): _row(metron="107"),
    }

    got = _found(_entry(comicvine="7"), comics)

    assert got["found"] == {"a": (FoundBy.ID, False)}
    assert got["planned"] == {"a"}


def test_a_loose_comic_agreeing_with_a_strong_match_is_kept() -> None:
    comics = {
        Path("a.cbz"): _row(comicvine="7", metron="101"),
        Path("b.cbz"): _row(metron="101"),
    }

    got = _found(_entry(comicvine="7"), comics)

    assert got["found"] == {"a": (FoundBy.ID, False), "b": (FoundBy.NAME_YEAR, False)}


def test_an_exact_loose_comic_whose_id_differs_from_a_strong_match_is_refused() -> None:
    """
    An entry with no year finds a bare volume-1 comic exactly; an id finds a.

    The bare comic has another Comic Vine id than a, the comic the entry's
    Metron id names, so it is refused, as a loose comic of another volume
    than a strong match is when no comic is exact.
    """
    comics = {
        Path("a.cbz"): _row(start_year=2016, volume=1, metron="101", comicvine="56"),
        Path("b.cbz"): _row(volume=1, comicvine="55"),
    }

    got = _found(_entry(volume=1, metron="101"), comics)

    assert got["found"] == {"a": (FoundBy.ID, False)}


def test_an_ambiguous_entry_says_which_ids_it_fits() -> None:
    buffer = io.StringIO()
    print_ambiguous(
        Console(file=buffer, width=200),
        Path("a.cbz"),
        0,
        (),
        (("metron", "101"), ("metron", "107")),
    )
    text = buffer.getvalue()
    assert "metron ids 101 and 107" in text
    assert "an id on the entry settles it" in text


# ---------------------------------------------------------------- B: combine


def _sources(*inputs: dict[str, Any]) -> list[set[tuple[int, int]]]:
    result = combine(list(inputs))
    groups = [
        {(origin.input_index, origin.row) for origin in origins}
        for origins in result.provenance
    ]
    return sorted(groups, key=sorted)


def test_a_repeated_bare_row_stays_its_own_entry_beside_two_volumes() -> None:
    """The fuzzer's case B: A's second copy joined B's second 2011 row."""
    bare = _row()
    first = _list(bare, bare)
    second = _list(_row(start_year=2011), _row(start_year=2016), _row(start_year=2011))

    groups = _sources(first, second)

    assert all(len(group) == 1 for group in groups), groups


def test_a_repeated_bare_volume_row_stays_its_own_entry_beside_two_years() -> None:
    """The volume key is linked by the same candidate rule."""
    bare = _row(volume=1)
    first = _list(bare, bare)
    second = _list(
        _row(start_year=1963, volume=1),
        _row(start_year=1991, volume=1),
        _row(start_year=1963, volume=1),
    )

    groups = _sources(first, second)

    assert all(len(group) == 1 for group in groups), groups


def test_repeated_bare_rows_still_pair_in_order_with_one_volume() -> None:
    """Every row of the other list fits one volume: copies pair in order."""
    bare = _row()
    first = _list(bare, bare)
    second = _list(_row(start_year=2011), _row(start_year=2011))

    assert _sources(first, second) == [{(0, 0), (1, 0)}, {(0, 1), (1, 1)}]


def test_a_list_repeating_a_bare_row_combines_with_itself_unchanged() -> None:
    reading_list = _list(_row(), _row(start_year=2011), _row())

    result = combine([reading_list, reading_list])

    assert [
        {(origin.input_index, origin.row) for origin in origins}
        for origins in result.provenance
    ] == [{(0, row), (1, row)} for row in range(3)]
