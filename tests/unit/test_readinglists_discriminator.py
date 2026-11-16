"""
The cover-year key compares like with like (R3-G).

A row's discriminator is its name key's: the start year, or the volume
number. Two can be compared when both are years or both are volume
numbers, and conflict when they can be compared and differ.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from comicbox.readinglists import (
    ENTRIES_KEY,
    Verdict,
    combine,
    compare,
    discriminator,
    discriminators_conflict,
    reading_lists_from_comics,
)
from comicbox.readinglists.match import match_comics, plan_arcs
from comicbox.readinglists.render import print_ambiguous, volumes_text

_COVER = date(2015, 1, 1)


def _entry(
    *,
    series: str = "The Unbeatable Squirrel Girl",
    start_year: int | None = None,
    volume: int | None = None,
    **fields: Any,
) -> dict[str, Any]:
    names: dict[str, Any] = {"name": series}
    if start_year is not None:
        names["start_year"] = start_year
    entry: dict[str, Any] = {
        "series": names,
        "issue": {"name": "1"},
        "date": {"cover_date": _COVER},
        **fields,
    }
    if volume is not None:
        entry["volume"] = {"number": volume}
    return entry


def _list(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"name": "Squirrel Girl", "ordered": True, ENTRIES_KEY: list(entries)}


def _groups(*inputs: dict[str, Any]) -> list[set[tuple[int, int]]]:
    """Combine lists; list the rows each combined entry came from."""
    return [
        {(origin.input_index, origin.row) for origin in origins}
        for origins in combine(list(inputs)).provenance
    ]


_VOL1 = _entry(volume=1)
_VOL2 = _entry(volume=2)
_BARE = _entry()


# --------------------------------------------------------- the conflict test


@pytest.mark.parametrize(
    ("one", "other", "conflict"),
    [
        (2011, 2016, True),
        (1, 2, True),
        (1, 1, False),
        (2016, 2016, False),
        # A start year and a small volume number cannot be compared.
        (2016, 2, False),
        (None, 1, False),
        (None, None, False),
    ],
)
def test_discriminators_conflict(
    one: int | None, other: int | None, *, conflict: bool
) -> None:
    assert discriminators_conflict(one, other) is conflict
    assert discriminators_conflict(other, one) is conflict


@pytest.mark.parametrize(
    ("entry", "value"),
    [
        (_entry(start_year=2015), 2015),
        (_entry(volume=2), 2),
        # The name key's: the start year first.
        (_entry(start_year=2015, volume=2), 2015),
        (_BARE, None),
        # No issue, so no name key.
        ({"series": {"name": "X"}, "volume": {"number": 2}}, None),
    ],
)
def test_the_discriminator_is_the_name_keys(
    entry: dict[str, Any], value: int | None
) -> None:
    assert discriminator(entry) == value


# ------------------------------------------------------------------ combine


def test_two_small_volumes_with_one_cover_year_stay_apart() -> None:
    """Squirrel Girl vol 1 #1 and vol 2 #1, both 2015, joined as one."""
    assert _groups(_list(_VOL1), _list(_VOL2)) == [{(0, 0)}, {(1, 0)}]
    assert compare(_list(_VOL1), _list(_VOL2)).verdict is Verdict.UNRELATED


@pytest.mark.parametrize("order", [(0, 1, 2), (0, 2, 1), (2, 0, 1), (2, 1, 0)])
def test_two_small_volumes_never_meet_through_a_cover_year_row(
    order: tuple[int, ...],
) -> None:
    rows = (_VOL1, _VOL2, _BARE)
    position = {row: order.index(row) for row in range(3)}

    groups = [
        {index for index, _ in group}
        for group in _groups(*(_list(rows[index]) for index in order))
    ]

    assert len(groups) == 2
    assert not any({position[0], position[1]} <= group for group in groups)


@pytest.mark.parametrize("bare_first", [False, True])
def test_the_cover_year_key_counts_repeats_for_each_discriminator(
    *, bare_first: bool
) -> None:
    """A row the guard refuses no longer uses up the occurrence another needs."""
    one = _entry(series="Avengers", start_year=2011)
    other = _entry(series="Avengers", start_year=2016)
    bare = _entry(series="Avengers")
    second = (bare, other) if bare_first else (other, bare)

    groups = _groups(_list(one), _list(*second))

    bare_row = 0 if bare_first else 1
    assert len(groups) == 2
    assert {(0, 0), (1, bare_row)} in groups


def test_from_arcs_keeps_two_volumes_with_one_cover_year_apart() -> None:
    comics = [
        {**_entry(series="Avengers", start_year=2011), "arcs": {"Standoff": {}}},
        {**_entry(series="Avengers", start_year=2016), "arcs": {"Standoff": {}}},
        {**_VOL1, "arcs": {"Standoff": {}}},
        {**_VOL2, "arcs": {"Standoff": {}}},
        # A copy of one is still one entry.
        {**_VOL2, "arcs": {"Standoff": {}}},
    ]

    (reading_list,) = reading_lists_from_comics(comics)

    assert len(reading_list[ENTRIES_KEY]) == 4


# -------------------------------------------------------------------- match


def test_a_cover_year_match_of_another_small_volume_is_refused() -> None:
    """write-arcs gave the volume-2 comic the volume-1 entry's number."""
    comics = {Path("vol2.cbz"): _VOL2}
    reading_list = _list(_VOL1)

    result = match_comics(reading_list, comics)

    assert result.found == ()
    assert plan_arcs(reading_list, comics, result, "Squirrel Girl") == ()


def test_an_entry_that_fits_two_small_volumes_is_ambiguous() -> None:
    comics = {Path("vol1.cbz"): _VOL1, Path("vol2.cbz"): _VOL2}
    reading_list = _list(_BARE)
    buffer = io.StringIO()

    result = match_comics(reading_list, comics)

    (found,) = result.found
    assert all(comic.ambiguous for comic in found.comics)
    assert found.volumes == (1, 2)
    assert plan_arcs(reading_list, comics, result, "Squirrel Girl") == ()
    print_ambiguous(Console(file=buffer, width=200), Path("vol1.cbz"), 0, found.volumes)
    assert (
        buffer.getvalue()
        .rstrip()
        .endswith("fits volumes 1 and 2 alike; a volume number on the entry settles it")
    )


def test_a_small_volume_beside_a_strong_match_of_another_is_refused() -> None:
    comics = {
        Path("vol1.cbz"): _VOL1,
        Path("vol2.cbz"): _entry(volume=2, identifiers={"metron": {"key": "7"}}),
    }
    reading_list = _list(_entry(identifiers={"metron": {"key": "7"}}))

    (found,) = match_comics(reading_list, comics).found

    assert found.paths == (Path("vol2.cbz"),)
    assert not found.ambiguous


@pytest.mark.parametrize(
    ("volumes", "text"),
    [
        ((2011, 2016), "the 2011 and 2016 volumes"),
        ((1, 2), "volumes 1 and 2"),
        ((1, 2, 2011), "the 2011 volume and volumes 1 and 2"),
    ],
)
def test_the_volumes_an_entry_fits_are_named(
    volumes: tuple[int, ...], text: str
) -> None:
    assert volumes_text(volumes) == text
