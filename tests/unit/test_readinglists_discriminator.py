"""
The cover-year key compares like with like (R3-G, R3-H, R3-I).

A row's signature has up to two discriminators, one of each kind: the
year-like one, its start year or a volume number of 1900 or more, and its
small volume number. Two rows conflict when they have one of the same kind
and those differ. Every exact pair is linked; a loose pair only when neither
row has an exact candidate in the other's list, each is the other's only
loose one there, and neither has two candidates that conflict.
"""

from __future__ import annotations

import io
import itertools
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from comicbox.readinglists import (
    ENTRIES_KEY,
    Discriminators,
    Verdict,
    combine,
    compare,
    discriminators,
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
    cover: date = _COVER,
    **fields: Any,
) -> dict[str, Any]:
    names: dict[str, Any] = {"name": series}
    if start_year is not None:
        names["start_year"] = start_year
    entry: dict[str, Any] = {
        "series": names,
        "issue": {"name": "1"},
        "date": {"cover_date": cover},
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
        (Discriminators(2011), Discriminators(2016), True),
        (Discriminators(volume=1), Discriminators(volume=2), True),
        (Discriminators(volume=1), Discriminators(volume=1), False),
        (Discriminators(2016), Discriminators(2016), False),
        # A start year and a small volume number cannot be compared.
        (Discriminators(2016), Discriminators(volume=2), False),
        (Discriminators(), Discriminators(volume=1), False),
        (Discriminators(), Discriminators(), False),
        # Both kinds: either one differing is enough.
        (Discriminators(1991, 2), Discriminators(volume=1), True),
        (Discriminators(1991, 2), Discriminators(2016, 2), True),
        (Discriminators(1991, 2), Discriminators(1991), False),
        (Discriminators(1991, 2), Discriminators(volume=2), False),
    ],
)
def test_two_rows_conflict_when_they_differ_in_a_kind_they_share(
    one: Discriminators, other: Discriminators, *, conflict: bool
) -> None:
    assert one.conflicts(other) is conflict
    assert other.conflicts(one) is conflict


@pytest.mark.parametrize(
    ("entry", "value"),
    [
        (_entry(start_year=2015), Discriminators(2015)),
        (_entry(volume=2), Discriminators(volume=2)),
        (_entry(start_year=1991, volume=2), Discriminators(1991, 2)),
        # A volume number of 1900 or more is year-like, as a CBL's is.
        (_entry(volume=2006), Discriminators(2006)),
        # The start year is the year-like one when there are two.
        (_entry(start_year=2011, volume=2016), Discriminators(2011)),
        (_BARE, Discriminators()),
    ],
)
def test_a_row_has_a_discriminator_of_each_kind(
    entry: dict[str, Any], value: Discriminators
) -> None:
    assert discriminators(entry) == value


# ------------------------------------------------------------------ combine


def test_two_small_volumes_with_one_cover_year_stay_apart() -> None:
    """Squirrel Girl vol 1 #1 and vol 2 #1, both 2015, joined as one."""
    assert _groups(_list(_VOL1), _list(_VOL2)) == [{(0, 0)}, {(1, 0)}]
    assert compare(_list(_VOL1), _list(_VOL2)).verdict is Verdict.UNRELATED


@pytest.mark.parametrize("order", [(0, 1, 2), (0, 2, 1), (2, 0, 1), (2, 1, 0)])
def test_two_small_volumes_never_meet_through_a_cover_year_row(
    order: tuple[int, ...],
) -> None:
    """The bare row fits both volumes, so it joins neither (R3-I)."""
    rows = (_VOL1, _VOL2, _BARE)

    groups = _groups(*(_list(rows[index]) for index in order))

    assert groups == [{(0, 0)}, {(1, 0)}, {(2, 0)}]


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


# ------------------------------------------------------- R3-H: two kinds

_XMEN_COVER = date(1991, 10, 1)
_XMEN_V2 = _entry(series="X-Men", start_year=1991, volume=2, cover=_XMEN_COVER)
_XMEN_V1 = _entry(series="X-Men", volume=1, cover=_XMEN_COVER)
_XMEN_BARE = _entry(series="X-Men", cover=_XMEN_COVER)


def test_a_row_with_both_discriminators_is_told_apart_by_its_volume() -> None:
    """X-Men (1991) volume 2 #1 and X-Men volume 1 #1, both 1991, joined."""
    assert _groups(_list(_XMEN_V2), _list(_XMEN_V1)) == [{(0, 0)}, {(1, 0)}]
    assert compare(_list(_XMEN_V2), _list(_XMEN_V1)).verdict is Verdict.UNRELATED


def test_a_row_with_both_still_joins_a_row_of_its_volume() -> None:
    same = _entry(series="X-Men", volume=2, cover=_XMEN_COVER)
    assert _groups(_list(_XMEN_V2), _list(same)) == [{(0, 0), (1, 0)}]


def test_a_cover_year_match_of_another_volume_number_is_refused() -> None:
    comics = {Path("v2.cbz"): _XMEN_V2}
    assert match_comics(_list(_XMEN_V1), comics).found == ()


def test_an_entry_that_fits_a_row_with_both_and_another_volume_is_ambiguous() -> None:
    comics = {Path("v1.cbz"): _XMEN_V1, Path("v2.cbz"): _XMEN_V2}

    (found,) = match_comics(_list(_XMEN_BARE), comics).found

    assert all(comic.ambiguous for comic in found.comics)
    assert found.volumes == (1, 2)


def test_beside_a_strong_match_a_cover_year_one_agrees_in_the_kind_they_share() -> None:
    metron = {"identifiers": {"metron": {"key": "7"}}}
    comics = {
        Path("strong.cbz"): {**_XMEN_V2, **metron},
        Path("vol1.cbz"): _XMEN_V1,
        Path("vol2.cbz"): _entry(series="X-Men", volume=2, cover=_XMEN_COVER),
        Path("y1991.cbz"): _entry(series="X-Men", start_year=1991, cover=_XMEN_COVER),
    }

    (found,) = match_comics(_list({**_XMEN_BARE, **metron}), comics).found

    assert found.paths == (Path("strong.cbz"), Path("vol2.cbz"), Path("y1991.cbz"))
    assert not found.ambiguous


# ---------------------------------- R3-H: a row that fits two conflicting rows

_AV_COVER = date(2016, 1, 1)
_AV2011 = _entry(series="Avengers", start_year=2011, cover=_AV_COVER)
_AV2016 = _entry(series="Avengers", start_year=2016, cover=_AV_COVER)
_AV_BARE = _entry(series="Avengers", cover=_AV_COVER)


@pytest.mark.parametrize("rows", list(itertools.permutations((_AV2011, _AV2016))))
def test_a_row_that_fits_two_rows_of_an_input_that_conflict_joins_neither(
    rows: tuple[dict[str, Any], ...],
) -> None:
    """A=[Avengers (2011) #1, Avengers (2016) #1], B=[Avengers #1]: B joined the first."""
    assert _groups(_list(*rows), _list(_AV_BARE)) == [{(0, 0)}, {(0, 1)}, {(1, 0)}]
    assert _groups(_list(_AV_BARE), _list(*rows)) == [{(0, 0)}, {(1, 0)}, {(1, 1)}]


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))), ids=str)
def test_from_arcs_folds_no_copy_it_cannot_place(order: tuple[int, ...]) -> None:
    rows = (_AV2011, _AV2016, _AV_BARE)
    comics = [{**rows[index], "arcs": {"Standoff": {}}} for index in order]

    (reading_list,) = reading_lists_from_comics(comics)

    assert len(reading_list[ENTRIES_KEY]) == 3


@pytest.mark.parametrize("bare_first", [False, True])
def test_from_arcs_still_folds_a_copy_into_its_one_volume(*, bare_first: bool) -> None:
    rows = (_AV_BARE, _AV2011) if bare_first else (_AV2011, _AV_BARE)
    comics = [{**row, "arcs": {"Standoff": {}}} for row in rows]

    (reading_list,) = reading_lists_from_comics(comics)

    assert len(reading_list[ENTRIES_KEY]) == 1


# ------------------------------------------------ R3-I: what the rule decides


def _entries(*inputs: dict[str, Any]) -> int:
    return len(combine(list(inputs)).reading_list[ENTRIES_KEY])


@pytest.mark.parametrize(
    "rows",
    [(_AV_BARE, _AV2011, _AV2016), (_BARE, _VOL1, _VOL2)],
    ids=["years", "volumes"],
)
def test_a_list_with_a_bare_row_and_two_volumes_combines_with_itself(
    rows: tuple[dict[str, Any], ...],
) -> None:
    """[bare, 2011, 2016] with itself became 4 entries and compared unrelated."""
    assert _groups(_list(*rows), _list(*rows)) == [{(0, r), (1, r)} for r in range(3)]
    assert compare(_list(*rows), _list(*rows)).verdict is Verdict.SAME


def test_a_loose_pair_alone_is_joined_and_a_conflicting_one_is_not() -> None:
    assert _entries(_list(_AV2011), _list(_AV2016)) == 2
    assert _entries(_list(_AV2011), _list(_AV_BARE)) == 1


def test_a_third_list_does_not_carry_a_bare_row_into_one_volume() -> None:
    groups = _groups(_list(_AV2011, _AV2016), _list(_AV_BARE), _list(_AV2011))
    assert {(1, 0)} in groups
    assert {(0, 0), (2, 0)} in groups


def test_a_bare_row_with_two_loose_candidates_in_a_list_stays_alone() -> None:
    cover = date(2015, 1, 1)
    started = _entry(series="X", start_year=1999, cover=cover)
    numbered = _entry(series="X", volume=2, cover=cover)
    bare = _entry(series="X", cover=cover)
    assert {(1, 0)} in _groups(_list(started, numbered), _list(bare))


def test_bare_rows_join_each_other_and_their_volumes_stay_apart() -> None:
    groups = _groups(_list(_AV_BARE, _AV2011), _list(_AV_BARE, _AV2016))
    assert sorted(groups, key=sorted) == [{(0, 0), (1, 0)}, {(0, 1)}, {(1, 1)}]


def test_one_start_year_with_two_volume_numbers_joins_by_the_name_key() -> None:
    """Design 3's name key, unchanged; the docs say so."""
    one = _entry(series="X-Men", start_year=1991, volume=1, cover=_XMEN_COVER)
    other = _entry(series="X-Men", start_year=1991, volume=2, cover=_XMEN_COVER)
    assert _entries(_list(one), _list(other)) == 1


# ------------------------- R3-I: the clauses no line of the plan's list shows


def test_a_row_whose_exact_copy_is_taken_does_not_fall_back_to_a_loose_one() -> None:
    """Rule 2: B's bare row joins A's 2016 row by id, so A's bare row stays alone."""
    metron = {"identifiers": {"metron": {"key": "7"}}}
    first = _list(_AV_BARE, {**_AV2016, **metron})
    second = _list({**_AV_BARE, **metron}, _AV2011)

    assert _groups(first, second) == [{(0, 0)}, {(0, 1), (1, 0)}, {(1, 1)}]


def test_an_exact_pair_never_joins_two_volumes_that_ids_hold() -> None:
    """Rule 3: the bare rows are exact, but their groups hold 2011 and 2016."""
    seven = {"identifiers": {"metron": {"key": "7"}}}
    eight = {"identifiers": {"metron": {"key": "8"}}}
    lists = (
        _list({**_AV_BARE, **seven}),
        _list({**_AV2011, **seven}),
        _list({**_AV_BARE, **eight}),
        _list({**_AV2016, **eight}),
    )

    assert _groups(*lists) == [{(0, 0), (1, 0)}, {(2, 0), (3, 0)}]


def test_match_finds_a_comic_of_the_entrys_own_signature_and_no_other() -> None:
    """R3-J: the bare comic is exact, so the 2011 and 2016 ones are not found."""
    comics = {
        Path("bare.cbz"): _AV_BARE,
        Path("v2011.cbz"): _AV2011,
        Path("v2016.cbz"): _AV2016,
    }

    (found,) = match_comics(_list(_AV_BARE), comics).found

    assert found.paths == (Path("bare.cbz"),)
    assert not found.ambiguous


# --------------------------------------- R3-J: match tags only the exact comic


def _tagged(reading_list: dict[str, Any], comics: dict[Path, Any]) -> list[str]:
    """Name the comics write-arcs would tag, in path order."""
    result = match_comics(reading_list, comics)
    return sorted(
        change.path.name for change in plan_arcs(reading_list, comics, result, "Arc")
    )


def test_a_bare_entry_tags_the_bare_comic_and_not_a_2011_one() -> None:
    """Entries [bare, 2016] over comics [bare, 2011]: both were tagged."""
    comics = {Path("bare.cbz"): _AV_BARE, Path("v2011.cbz"): _AV2011}
    assert _tagged(_list(_AV_BARE, _AV2016), comics) == ["bare.cbz"]


def test_an_entry_of_2016_tags_the_2016_comic_and_not_a_bare_one() -> None:
    comics = {Path("v2016.cbz"): _AV2016, Path("bare.cbz"): _AV_BARE}

    (found,) = match_comics(_list(_AV2016), comics).found

    assert found.paths == (Path("v2016.cbz"),)
    assert _tagged(_list(_AV2016), comics) == ["v2016.cbz"]


def test_a_bare_entry_over_a_single_2011_comic_still_finds_it() -> None:
    assert _tagged(_list(_AV_BARE), {Path("v2011.cbz"): _AV2011}) == ["v2011.cbz"]


def test_two_files_of_the_exact_comic_are_both_tagged() -> None:
    comics = {
        Path("a/v2016.cbz"): _AV2016,
        Path("b/v2016.cbz"): _AV2016,
        Path("bare.cbz"): _AV_BARE,
    }
    assert _tagged(_list(_AV2016), comics) == ["v2016.cbz", "v2016.cbz"]


def test_an_exact_comic_found_by_id_leaves_out_a_loose_one() -> None:
    """By any key: the bare comic has the entry's Metron id and its signature."""
    metron = {"identifiers": {"metron": {"key": "7"}}}
    comics = {Path("bare.cbz"): {**_AV_BARE, **metron}, Path("v2011.cbz"): _AV2011}

    (found,) = match_comics(_list({**_AV_BARE, **metron}), comics).found

    assert found.paths == (Path("bare.cbz"),)
