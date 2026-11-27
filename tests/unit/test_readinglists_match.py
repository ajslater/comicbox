"""Matching a list against comics' tags, and planning their arcs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import (
    entry_keys,
    name_variants,
    reading_lists_from_comics,
)
from comicbox.readinglists.match import (
    ArcAction,
    FoundBy,
    match_comics,
    plan_arcs,
)


def _tags(series: str, number: str, **fields: Any) -> dict[str, Any]:
    tags: dict[str, Any] = {"series": {"name": series}, "issue": {"name": number}}
    if (start_year := fields.get("start_year")) is not None:
        tags["series"]["start_year"] = start_year
    if (year := fields.get("year")) is not None:
        tags["date"] = {"cover_date": date(year, 1, 1)}
    if ids := fields.get("ids"):
        tags["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    if arcs := fields.get("arcs"):
        tags["arcs"] = arcs
    return tags


def _entry(series: str, number: str, **fields: Any) -> dict[str, Any]:
    return _tags(series, number, **fields)


def _list(*entries: dict[str, Any], **header: Any) -> dict[str, Any]:
    return {"name": "Crimson Tide", "entries": list(entries), **header}


# ------------------------------------------------------------- variants


@pytest.mark.parametrize(
    ("series", "start_year", "variants"),
    [
        # A year or volume is never added to the name.
        ("Crimson Tide", 2006, ("crimson tide",)),
        ("Bladehawk (2016)", 2016, ("bladehawk 2016", "bladehawk")),
        ("Sonnet (v2)", 2012, ("sonnet v2", "sonnet")),
        ("Sonnet (Vol. 2)", 2012, ("sonnet",)),
        # Only a year or volume is taken off: "(UK)" names another series.
        ("Trundlebots (UK)", 1984, ("trundlebots uk",)),
        (
            "The Amazing Snail-Man",
            1963,
            ("the amazing snail man", "amazing snail man"),
        ),
        ("Sonnet TPB", 2012, ("sonnet tpb", "sonnet")),
        ("Sonnet Omnibus", None, ("sonnet omnibus", "sonnet")),
        # A hyphenated "A" is part of the name, not an article.
        ("A-Force", 2015, ("a force",)),
        # Each step is also taken from the ones before: suffix, year, article.
        (
            "The Bladehawk (2016) TPB",
            2016,
            (
                "the bladehawk 2016 tpb",
                "the bladehawk 2016",
                "the bladehawk",
                "bladehawk 2016 tpb",
                "bladehawk 2016",
                "bladehawk",
            ),
        ),
    ],
)
def test_name_variants_in_design_order(
    series: str, start_year: int | None, variants: tuple[str, ...]
) -> None:
    entry = _entry(series, "1", start_year=start_year)
    assert name_variants(entry) == variants


def test_entry_keys_stay_strict() -> None:
    """Variants are for matching comics only: combine never joins on them."""
    entry = _entry("The Amazing Snail-Man", "1", start_year=1963)
    assert entry_keys(entry) == (
        ("name", "the amazing snail man", "year", 1963, Decimal(1), ""),
    )


# ---------------------------------------------------------------- match


def _found(result: Any) -> dict[int, dict[str, FoundBy]]:
    return {
        found.position: {comic.path.name: comic.by for comic in found.comics}
        for found in result.found
    }


def test_an_id_and_a_name_both_find_their_comics() -> None:
    comics = {
        Path("by-id.cbz"): _tags("Other Name", "9", ids={"comicvine": "105747"}),
        Path("by-name.cbz"): _tags("Crimson Tide", "1", start_year=2006),
    }
    entry = _entry("Crimson Tide", "1", start_year=2006, ids={"comicvine": "105747"})

    result = match_comics(_list(entry), comics)

    assert _found(result) == {0: {"by-id.cbz": FoundBy.ID, "by-name.cbz": FoundBy.NAME}}


def test_a_copy_without_the_id_is_found_beside_one_with_it() -> None:
    """The id match used to end the search, dropping the copy without one."""
    comics = {
        Path("a/cw1.cbz"): _tags(
            "Crimson Tide", "1", start_year=2006, ids={"comicvine": "1"}
        ),
        Path("b/cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006),
    }
    entry = _entry("Crimson Tide", "1", start_year=2006, ids={"comicvine": "1"})

    (found,) = match_comics(_list(entry), comics).found

    assert found.paths == (Path("a/cw1.cbz"), Path("b/cw1.cbz"))


def test_every_copy_of_an_issue_is_found_whatever_its_year() -> None:
    """The cover year cut three copies of one issue down to one."""
    comics = {
        Path("a.cbz"): _tags("Crimson Tide", "1", start_year=2006, year=2006),
        Path("b.cbz"): _tags("Crimson Tide", "1", start_year=2006, year=2007),
        Path("c.cbz"): _tags("Crimson Tide", "1", start_year=2006),
    }
    entry = _entry("Crimson Tide", "1", start_year=2006, year=2006)

    (found,) = match_comics(_list(entry), comics).found

    assert found.paths == (Path("a.cbz"), Path("b.cbz"), Path("c.cbz"))


@pytest.mark.parametrize(
    ("comic_ids", "year"),
    [
        ({"comicvine": "2"}, 2006),
        # One database agrees, another does not: still two issues.
        ({"comicvine": "1", "metron": "8"}, 2006),
        # Cover years more than a year apart.
        ({}, 2008),
    ],
)
def test_a_contradiction_vetoes_a_match(comic_ids: dict[str, str], year: int) -> None:
    comics = {
        Path("cw1.cbz"): _tags(
            "Crimson Tide", "1", start_year=2006, ids=comic_ids, year=year
        )
    }
    entry = _entry(
        "Crimson Tide",
        "1",
        start_year=2006,
        ids={"comicvine": "1", "metron": "7"},
        year=2006,
    )

    result = match_comics(_list(entry), comics)

    assert result.found == ()
    assert result.missing == (0,)


# A comic's 17-digit UPC: the title's 12 digits and a 5-digit supplement for
# the issue, cover and printing. These two differ only in the cover digit.
_UPC_A = "75960608936800111"
_UPC_B = "75960608936800121"


def test_a_differing_barcode_never_vetoes_an_id_match() -> None:
    """A variant cover's UPC made metron 5 miss its own comic."""
    comics = {
        Path("b.cbz"): _tags(
            "Bladehawk",
            "1",
            start_year=2016,
            year=2016,
            ids={"metron": "5", "upc": _UPC_B},
        )
    }
    entry = _entry(
        "Bladehawk", "1", start_year=2016, year=2016, ids={"metron": "5", "upc": _UPC_A}
    )

    assert _found(match_comics(_list(entry), comics)) == {0: {"b.cbz": FoundBy.ID}}


def test_variant_covers_from_arcs_are_all_found_and_planned() -> None:
    """from-arcs folds two covers into one entry; match found only one of them."""
    comics = {
        Path(f"{name}.cbz"): _tags(
            "Bladehawk",
            "1",
            start_year=2016,
            year=2016,
            ids={"metron": "5", "upc": upc},
            arcs={"Saga": {"number": 1}},
        )
        for name, upc in (("a", _UPC_A), ("b", _UPC_B))
    }
    (reading_list,) = reading_lists_from_comics(comics.values())

    result = match_comics(reading_list, comics)

    assert result.missing == ()
    assert _found(result) == {0: {"a.cbz": FoundBy.ID, "b.cbz": FoundBy.ID}}
    plan = plan_arcs(reading_list, comics, result, "Saga")
    assert [change.path.name for change in plan] == ["a.cbz", "b.cbz"]


def test_a_barcode_alone_still_finds_its_comic() -> None:
    comics = {Path("b.cbz"): _tags("Other Name", "9", ids={"upc": _UPC_B})}
    entry = {"identifiers": {"upc": {"key": _UPC_B}}}

    assert _found(match_comics(_list(entry), comics)) == {0: {"b.cbz": FoundBy.ID}}


def test_a_differing_metron_id_still_vetoes_beside_a_shared_barcode() -> None:
    comics = {
        Path("b.cbz"): _tags(
            "Bladehawk", "1", start_year=2016, ids={"metron": "6", "upc": _UPC_A}
        )
    }
    entry = _entry(
        "Bladehawk", "1", start_year=2016, ids={"metron": "5", "upc": _UPC_A}
    )

    assert match_comics(_list(entry), comics).missing == (0,)


def test_cover_years_a_year_apart_still_match() -> None:
    comics = {Path("cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006, year=2007)}
    entry = _entry("Crimson Tide", "1", start_year=2006, year=2006)
    assert _found(match_comics(_list(entry), comics)) == {0: {"cw1.cbz": FoundBy.NAME}}


def test_a_contradiction_vetoes_a_variant_too() -> None:
    comics = {
        Path("asm.cbz"): _tags(
            "The Amazing Snail-Man", "1", start_year=1963, ids={"metron": "2"}
        )
    }
    entry = _entry("Amazing Snail-Man", "1", start_year=1963, ids={"metron": "1"})
    assert match_comics(_list(entry), comics).found == ()


@pytest.mark.parametrize(
    ("entry_series", "comic_series"),
    [
        ("Amazing Snail-Man", "The Amazing Snail-Man"),
        ("The Amazing Snail-Man", "Amazing Snail-Man"),
        ("Bladehawk", "Bladehawk (2016)"),
        ("Bladehawk (2016)", "Bladehawk"),
        ("Sonnet", "Sonnet TPB"),
        # Variants compose: each step is taken from the one before.
        ("The Bladehawk (2016)", "Bladehawk"),
        ("Bladehawk (2016) TPB", "Bladehawk"),
        ("The Bladehawk (2016) TPB", "Bladehawk"),
    ],
)
def test_a_name_variant_matches(entry_series: str, comic_series: str) -> None:
    year = 2016
    comics = {Path("comic.cbz"): _tags(comic_series, "1", start_year=year)}

    result = match_comics(_list(_entry(entry_series, "1", start_year=year)), comics)

    assert _found(result) == {0: {"comic.cbz": FoundBy.VARIANT}}
    assert result.missing == ()


@pytest.mark.parametrize(
    ("entry_series", "comic_series"),
    [
        # "(UK)" is not a year or volume, so it is never taken off.
        ("Trundlebots", "Trundlebots (UK)"),
        ("Trundlebots (UK)", "Trundlebots"),
        # A year is never added: Ivory Knight (2020) is not the series Ivory Knight 2020.
        ("Ivory Knight", "Ivory Knight 2020"),
        ("The Ivory Knight TPB", "Ivory Knight 2020"),
    ],
)
def test_a_name_that_is_another_series_never_matches(
    entry_series: str, comic_series: str
) -> None:
    comics = {Path("comic.cbz"): _tags(comic_series, "1", start_year=2020)}
    entry = _entry(entry_series, "1", start_year=2020)
    assert match_comics(_list(entry), comics).found == ()


def test_the_exact_name_beats_a_variant() -> None:
    comics = {
        Path("a/the.cbz"): _tags("The Fizz", "1", start_year=2016),
        Path("b/plain.cbz"): _tags("Fizz", "1", start_year=2016),
    }
    result = match_comics(_list(_entry("Fizz", "1", start_year=2016)), comics)
    assert _found(result) == {0: {"plain.cbz": FoundBy.NAME}}


def test_strict_matches_are_settled_before_any_variant() -> None:
    """sonnet1.cbz used to be an earlier "Sonnet TPB" entry's variant, not its own."""
    comics = {Path("sonnet1.cbz"): _tags("Sonnet", "1", start_year=2012)}
    entries = [
        _entry("Sonnet TPB", "1", start_year=2012),
        _entry("Sonnet", "1", start_year=2012),
    ]

    result = match_comics(_list(*entries), comics)

    assert _found(result) == {1: {"sonnet1.cbz": FoundBy.NAME}}
    assert result.missing == (0,)


def test_the_cover_year_breaks_a_tie_between_series() -> None:
    comics = {
        Path("a.cbz"): _tags("The Fizz", "1", start_year=2016, year=2016),
        Path("b.cbz"): _tags("Fizz TPB", "1", start_year=2016, year=2017),
    }
    entry = _entry("Fizz", "1", start_year=2016, year=2016)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("a.cbz"),)


@pytest.mark.parametrize("other_series", [False, True])
def test_the_cover_year_keeps_every_copy_of_one_series(other_series: bool) -> None:
    comics = {
        Path("a.cbz"): _tags("The Fizz", "1", start_year=2016, year=2016),
        Path("b.cbz"): _tags("The Fizz", "1", start_year=2016, year=2017),
    }
    if other_series:
        comics[Path("c.cbz")] = _tags("Fizz TPB", "1", start_year=2016, year=2017)
    entry = _entry("Fizz", "1", start_year=2016, year=2016)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("a.cbz"), Path("b.cbz"))


def test_two_files_of_one_issue_are_both_found() -> None:
    comics = {
        Path("cw1.cbr"): _tags("Crimson Tide", "1", start_year=2006, year=2006),
        Path("cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006, year=2006),
    }
    entry = _entry("Crimson Tide", "1", start_year=2006, year=2006)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("cw1.cbr"), Path("cw1.cbz"))


def test_an_entry_with_no_key_never_matches() -> None:
    """No id and no start year or volume: the rule AJ has not changed."""
    comics = {Path("bladehawk.cbz"): _tags("Bladehawk", "1", start_year=2016)}
    result = match_comics(_list(_entry("Bladehawk", "1")), comics)
    assert result.found == ()
    assert result.missing == (0,)


def test_missing_entries_are_named_by_position() -> None:
    comics = {Path("cw2.cbz"): _tags("Crimson Tide", "2", start_year=2006)}
    entries = [_entry("Crimson Tide", str(n), start_year=2006) for n in (1, 2, 3)]
    result = match_comics(_list(*entries), comics)
    assert [found.position for found in result.found] == [1]
    assert result.missing == (0, 2)


# ---------------------------------------------------------------- plan


def _plan(reading_list: dict[str, Any], comics: dict[Path, dict[str, Any]]) -> Any:
    return plan_arcs(
        reading_list, comics, match_comics(reading_list, comics), "Crimson Tide"
    )


def test_an_ordered_list_numbers_by_position() -> None:
    comics = {
        Path(f"cw{n}.cbz"): _tags("Crimson Tide", str(n), start_year=2006)
        for n in (1, 2)
    }
    entries = [_entry("Crimson Tide", str(n), start_year=2006) for n in (2, 1)]
    plan = _plan(_list(*entries), comics)
    assert [(change.path.name, change.number) for change in plan] == [
        ("cw1.cbz", 2),
        ("cw2.cbz", 1),
    ]
    assert {change.action for change in plan} == {ArcAction.ADD}


def test_an_unordered_list_writes_no_number() -> None:
    comics = {Path("cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006)}
    (change,) = _plan(
        _list(_entry("Crimson Tide", "1", start_year=2006), ordered=False), comics
    )
    assert change.number is None
    assert change.action is ArcAction.ADD


@pytest.mark.parametrize(
    ("arcs", "action", "current", "arc"),
    [
        ({"Crimson Tide": {"number": 1}}, ArcAction.TAGGED, 1, "Crimson Tide"),
        ({"Crimson Tide": {"number": 4}}, ArcAction.RENUMBER, 4, "Crimson Tide"),
        # Its own spelling is kept, so the comic never has the arc twice.
        ({"crimson tide": {"number": 4}}, ArcAction.RENUMBER, 4, "crimson tide"),
        ({"Other": {"number": 1}}, ArcAction.ADD, None, "Crimson Tide"),
    ],
)
def test_a_comic_that_has_the_arc(
    arcs: dict[str, Any], action: ArcAction, current: int | None, arc: str
) -> None:
    comics = {Path("cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006, arcs=arcs)}
    (change,) = _plan(_list(_entry("Crimson Tide", "1", start_year=2006)), comics)
    assert (change.action, change.current, change.arc) == (action, current, arc)


def test_an_issue_read_twice_takes_its_first_place_in_every_copy() -> None:
    comics = {
        Path(f"{copy}/cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006)
        for copy in "ab"
    }
    entries = [
        _entry("Crimson Tide", "1", start_year=2006),
        _entry("Crimson Tide", "2", start_year=2006),
        _entry("Crimson Tide", "1", start_year=2006),
    ]
    reading_list = _list(*entries)

    result = match_comics(reading_list, comics)

    # The later entry is found in the same comics.
    assert {found.position: found.paths for found in result.found} == {
        0: (Path("a/cw1.cbz"), Path("b/cw1.cbz")),
        2: (Path("a/cw1.cbz"), Path("b/cw1.cbz")),
    }
    assert [change.number for change in _plan(reading_list, comics)] == [1, 1]


def test_a_variant_is_planned_only_when_asked() -> None:
    comics = {
        Path("asm.cbz"): _tags("The Amazing Snail-Man", "1", start_year=1963),
        Path("cw1.cbz"): _tags("Crimson Tide", "1", start_year=2006),
    }
    reading_list = _list(
        _entry("Crimson Tide", "1", start_year=2006),
        _entry("Amazing Snail-Man", "1", start_year=1963),
    )
    result = match_comics(reading_list, comics)

    def planned(*, variants: bool) -> list[str]:
        changes = plan_arcs(
            reading_list, comics, result, "Crimson Tide", variants=variants
        )
        return [change.path.name for change in changes]

    assert planned(variants=False) == ["cw1.cbz"]
    assert planned(variants=True) == ["asm.cbz", "cw1.cbz"]


def test_a_cover_date_that_is_not_a_date_vetoes_nothing() -> None:
    comics = {
        Path("a.cbz"): _tags("Sonnet", "1", start_year=2012),
        Path("b.cbz"): _tags("Sonnet", "1", start_year=2012),
    }
    comics[Path("a.cbz")]["date"] = {"cover_date": "2012-01-01"}
    entry = _entry("Sonnet", "1", start_year=2012, year=2012)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("a.cbz"), Path("b.cbz"))


def test_a_keyless_entry_never_matches_a_keyless_comic() -> None:
    """Neither side has a year or volume: a name and number alone join nothing."""
    comics = {Path("bladehawk.cbz"): _tags("The Bladehawk", "1")}
    for series in ("Bladehawk", "The Bladehawk"):
        assert match_comics(_list(_entry(series, "1")), comics).found == ()
