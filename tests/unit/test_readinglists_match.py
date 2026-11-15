"""Matching a list against comics' tags, and planning their arcs."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from comicbox.readinglists import entry_keys, name_variants
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
    return {"name": "Civil War", "entries": list(entries), **header}


# ------------------------------------------------------------- variants


@pytest.mark.parametrize(
    ("series", "start_year", "variants"),
    [
        ("Civil War", 2006, ("civil war", "civil war 2006")),
        ("Batman (2016)", 2016, ("batman 2016", "batman")),
        (
            "The Amazing Spider-Man",
            1963,
            (
                "the amazing spider man",
                "the amazing spider man 1963",
                "amazing spider man",
            ),
        ),
        ("Saga TPB", 2012, ("saga tpb", "saga tpb 2012", "saga")),
        ("Saga Omnibus", None, ("saga omnibus", "saga")),
        # A hyphenated "A" is part of the name, not an article.
        ("A-Force", 2015, ("a force", "a force 2015")),
    ],
)
def test_name_variants_in_design_order(
    series: str, start_year: int | None, variants: tuple[str, ...]
) -> None:
    entry = _entry(series, "1", start_year=start_year)
    assert name_variants(entry) == variants


def test_entry_keys_stay_strict() -> None:
    """Variants are for matching comics only: combine never joins on them."""
    entry = _entry("The Amazing Spider-Man", "1", start_year=1963)
    assert entry_keys(entry) == (
        ("name", "the amazing spider man", 1963, *entry_keys(entry)[0][3:]),
    )


# ---------------------------------------------------------------- match


def test_an_id_is_the_strongest_match() -> None:
    comics = {
        Path("by-id.cbz"): _tags("Other Name", "9", ids={"comicvine": "105747"}),
        Path("by-name.cbz"): _tags("Civil War", "1", start_year=2006),
    }
    entry = _entry("Civil War", "1", start_year=2006, ids={"comicvine": "105747"})

    (found,) = match_comics(_list(entry), comics).found

    assert found.paths == (Path("by-id.cbz"),)
    assert found.by is FoundBy.ID


@pytest.mark.parametrize(
    ("entry_series", "comic_series"),
    [
        ("Amazing Spider-Man", "The Amazing Spider-Man"),
        ("The Amazing Spider-Man", "Amazing Spider-Man"),
        ("Batman", "Batman (2016)"),
        ("Batman (2016)", "Batman"),
        ("Saga", "Saga TPB"),
    ],
)
def test_a_name_variant_matches(entry_series: str, comic_series: str) -> None:
    year = 2016
    comics = {Path("comic.cbz"): _tags(comic_series, "1", start_year=year)}

    result = match_comics(_list(_entry(entry_series, "1", start_year=year)), comics)

    (found,) = result.found
    assert found.by is FoundBy.VARIANT
    assert result.missing == ()


def test_the_exact_name_beats_a_variant() -> None:
    comics = {
        Path("a/the.cbz"): _tags("The Flash", "1", start_year=2016),
        Path("b/plain.cbz"): _tags("Flash", "1", start_year=2016),
    }
    (found,) = match_comics(_list(_entry("Flash", "1", start_year=2016)), comics).found
    assert found.paths == (Path("b/plain.cbz"),)
    assert found.by is FoundBy.NAME


def test_the_cover_year_breaks_a_tie() -> None:
    comics = {
        Path("a.cbz"): _tags("Saga", "1", start_year=2012, year=2012),
        Path("b.cbz"): _tags("Saga", "1", start_year=2012, year=2019),
    }
    entry = _entry("Saga", "1", start_year=2012, year=2019)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("b.cbz"),)


def test_two_files_of_one_issue_are_both_found() -> None:
    comics = {
        Path("cw1.cbr"): _tags("Civil War", "1", start_year=2006, year=2006),
        Path("cw1.cbz"): _tags("Civil War", "1", start_year=2006, year=2006),
    }
    entry = _entry("Civil War", "1", start_year=2006, year=2006)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("cw1.cbr"), Path("cw1.cbz"))


def test_an_entry_with_no_key_never_matches() -> None:
    """No id and no start year or volume: the rule AJ has not changed."""
    comics = {Path("batman.cbz"): _tags("Batman", "1", start_year=2016)}
    result = match_comics(_list(_entry("Batman", "1")), comics)
    assert result.found == ()
    assert result.missing == (0,)


def test_missing_entries_are_named_by_position() -> None:
    comics = {Path("cw2.cbz"): _tags("Civil War", "2", start_year=2006)}
    entries = [_entry("Civil War", str(n), start_year=2006) for n in (1, 2, 3)]
    result = match_comics(_list(*entries), comics)
    assert [found.position for found in result.found] == [1]
    assert result.missing == (0, 2)


# ---------------------------------------------------------------- plan


def _plan(reading_list: dict[str, Any], comics: dict[Path, dict[str, Any]]) -> Any:
    return plan_arcs(
        reading_list, comics, match_comics(reading_list, comics), "Civil War"
    )


def test_an_ordered_list_numbers_by_position() -> None:
    comics = {
        Path(f"cw{n}.cbz"): _tags("Civil War", str(n), start_year=2006) for n in (1, 2)
    }
    entries = [_entry("Civil War", str(n), start_year=2006) for n in (2, 1)]
    plan = _plan(_list(*entries), comics)
    assert [(change.path.name, change.number) for change in plan] == [
        ("cw1.cbz", 2),
        ("cw2.cbz", 1),
    ]
    assert {change.action for change in plan} == {ArcAction.ADD}


def test_an_unordered_list_writes_no_number() -> None:
    comics = {Path("cw1.cbz"): _tags("Civil War", "1", start_year=2006)}
    (change,) = _plan(
        _list(_entry("Civil War", "1", start_year=2006), ordered=False), comics
    )
    assert change.number is None
    assert change.action is ArcAction.ADD


@pytest.mark.parametrize(
    ("arcs", "action", "current", "arc"),
    [
        ({"Civil War": {"number": 1}}, ArcAction.TAGGED, 1, "Civil War"),
        ({"Civil War": {"number": 4}}, ArcAction.RENUMBER, 4, "Civil War"),
        # Its own spelling is kept, so the comic never has the arc twice.
        ({"civil war": {"number": 4}}, ArcAction.RENUMBER, 4, "civil war"),
        ({"Other": {"number": 1}}, ArcAction.ADD, None, "Civil War"),
    ],
)
def test_a_comic_that_has_the_arc(
    arcs: dict[str, Any], action: ArcAction, current: int | None, arc: str
) -> None:
    comics = {Path("cw1.cbz"): _tags("Civil War", "1", start_year=2006, arcs=arcs)}
    (change,) = _plan(_list(_entry("Civil War", "1", start_year=2006)), comics)
    assert (change.action, change.current, change.arc) == (action, current, arc)


def test_an_issue_read_twice_takes_its_first_place() -> None:
    comics = {Path("cw1.cbz"): _tags("Civil War", "1", start_year=2006)}
    entries = [
        _entry("Civil War", "1", start_year=2006),
        _entry("Civil War", "2", start_year=2006),
        _entry("Civil War", "1", start_year=2006),
    ]
    (change,) = _plan(_list(*entries), comics)
    assert change.number == 1


def test_a_cover_date_that_is_not_a_date_breaks_no_tie() -> None:
    comics = {
        Path("a.cbz"): _tags("Saga", "1", start_year=2012),
        Path("b.cbz"): _tags("Saga", "1", start_year=2012),
    }
    comics[Path("a.cbz")]["date"] = {"cover_date": "2012-01-01"}
    entry = _entry("Saga", "1", start_year=2012, year=2012)
    (found,) = match_comics(_list(entry), comics).found
    assert found.paths == (Path("a.cbz"), Path("b.cbz"))


def test_a_keyless_entry_never_matches_a_keyless_comic() -> None:
    """Neither side has a year or volume: a name and number alone join nothing."""
    comics = {Path("batman.cbz"): _tags("The Batman", "1")}
    for series in ("Batman", "The Batman"):
        assert match_comics(_list(_entry(series, "1")), comics).found == ()
