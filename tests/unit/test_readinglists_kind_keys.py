"""
A name key per kind of discriminator, and the comics a missing entry refused.

Codex issue 1053: an entry with only ``volume 2`` missed a comic tagged
``start_year 2011, volume 2``, because the name key held the start year
before the volume number. An entry now has a year key and a volume key, and
a volume key never joins two years.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from comicbox.readinglists import (
    ENTRIES_KEY,
    Refused,
    RefusedReason,
    Verdict,
    combine,
    compare,
    entry_keys,
    reading_lists_from_comics,
)
from comicbox.readinglists.identity import variant_keys
from comicbox.readinglists.match import FoundBy, match_comics, plan_arcs

_COVER = date(2011, 11, 1)


def _entry(
    *,
    series: str = "Bladehawk",
    start_year: int | None = None,
    volume: int | None = None,
    cover: date | None = _COVER,
    issue: str = "1",
    **fields: Any,
) -> dict[str, Any]:
    names: dict[str, Any] = {"name": series}
    if start_year is not None:
        names["start_year"] = start_year
    entry: dict[str, Any] = {"series": names, "issue": {"name": issue}, **fields}
    if cover is not None:
        entry["date"] = {"cover_date": cover}
    if volume is not None:
        entry["volume"] = {"number": volume}
    return entry


def _list(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"name": "Bladehawk", "ordered": True, ENTRIES_KEY: list(entries)}


def _name_keys(entry: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [key for key in entry_keys(entry) if key[0] == "name"]


def _groups(*inputs: dict[str, Any]) -> list[set[tuple[int, int]]]:
    return sorted(
        (
            {(origin.input_index, origin.row) for origin in origins}
            for origins in combine(list(inputs)).provenance
        ),
        key=sorted,
    )


_V2 = _entry(volume=2, cover=None)
_2011_V2 = _entry(start_year=2011, volume=2)
_ZMEN_1963 = _entry(series="Z-Men", start_year=1963, volume=1, cover=None)
_ZMEN_1991 = _entry(series="Z-Men", start_year=1991, volume=1, cover=None)


# ------------------------------------------------------------------ the keys


def test_an_entry_has_a_year_key_then_a_volume_key() -> None:
    assert _name_keys(_2011_V2) == [
        ("name", "bladehawk", "year", 2011, Decimal(1), ""),
        ("name", "bladehawk", "volume", 2, Decimal(1), ""),
    ]


def test_volume_2_is_not_year_2() -> None:
    assert not set(_name_keys(_V2)) & set(_name_keys(_entry(start_year=2)))


def test_a_year_like_volume_is_a_year_key() -> None:
    assert _name_keys(_entry(volume=2011)) == _name_keys(_entry(start_year=2011))


def test_variant_keys_keep_both_kinds_for_each_name() -> None:
    entry = _entry(series="The Bladehawk (2011)", start_year=2011, volume=2)
    assert variant_keys(entry) == tuple(
        ("name", name, kind, value, Decimal(1), "")
        for name in ("the bladehawk 2011", "the bladehawk", "bladehawk 2011")
        for kind, value in (("year", 2011), ("volume", 2))
    )


# --------------------------------------------------------------- match_comics


def test_a_volume_only_entry_finds_a_comic_with_a_start_year() -> None:
    """The issue's case: undated, volume 2 only, against a 2011 v2 comic."""
    result = match_comics(_list(_V2), {Path("b.cbz"): _2011_V2})

    (found,) = result.found
    assert found.paths == (Path("b.cbz"),)
    assert found.comics[0].by is FoundBy.NAME


def test_a_volume_key_match_of_another_year_is_refused() -> None:
    comics = {Path("1963.cbz"): _ZMEN_1963, Path("1991.cbz"): _ZMEN_1991}

    (found,) = match_comics(_list(_ZMEN_1991), comics).found

    assert found.paths == (Path("1991.cbz"),)
    assert match_comics(_list(_ZMEN_1991), {Path("a.cbz"): _ZMEN_1963}).missing == (0,)


def test_a_year_like_volume_and_a_start_year_still_meet() -> None:
    result = match_comics(_list(_entry(volume=2011)), {Path("b.cbz"): _2011_V2})
    assert result.found[0].paths == (Path("b.cbz"),)


def test_a_variant_on_the_volume_key_of_another_year_is_refused() -> None:
    entry = _entry(series="Z-Men (Vol. 1)", start_year=1991, volume=1, cover=None)
    assert match_comics(_list(entry), {Path("a.cbz"): _ZMEN_1963}).missing == (0,)


# ------------------------------------------------------- combine and compare


def test_a_volume_only_row_joins_the_row_with_a_start_year() -> None:
    assert _groups(_list(_V2), _list(_2011_V2)) == [{(0, 0), (1, 0)}]


def test_two_volumes_of_one_name_stay_apart() -> None:
    assert _groups(_list(_ZMEN_1963), _list(_ZMEN_1991)) == [{(0, 0)}, {(1, 0)}]


def test_a_volume_only_row_does_not_carry_two_years_into_one_group() -> None:
    """It fits both years, so it joins neither (rl-core-3); it joined the first."""
    bare_v1 = _entry(series="Z-Men", volume=1, cover=None)
    groups = _groups(_list(bare_v1), _list(_ZMEN_1963), _list(_ZMEN_1991))
    assert groups == [{(0, 0)}, {(1, 0)}, {(2, 0)}]


def test_compare_keeps_two_volumes_apart() -> None:
    assert compare(_list(_ZMEN_1963), _list(_ZMEN_1991)).verdict is Verdict.UNRELATED
    assert compare(_list(_V2), _list(_2011_V2)).verdict is Verdict.SAME


# ------------------------------------------------------------------- refused


def test_a_cover_year_match_of_another_volume_is_refused_and_reported() -> None:
    entry = _entry(start_year=2016)
    result = match_comics(_list(entry), {Path("b.cbz"): _entry(start_year=2011)})

    assert result.missing == (0,)
    assert result.refused == (Refused(0, Path("b.cbz"), RefusedReason.OTHER_VOLUME),)


def test_a_name_match_off_by_its_cover_year_is_reported() -> None:
    comic = _entry(start_year=2011, cover=date(2016, 1, 1))
    result = match_comics(_list(_entry(start_year=2011)), {Path("b.cbz"): comic})

    assert result.missing == (0,)
    assert result.refused == (Refused(0, Path("b.cbz"), RefusedReason.COVER_YEAR),)


def test_a_comic_with_a_contradicting_id_is_not_reported() -> None:
    entry = _entry(start_year=2011, identifiers={"metron": {"key": "1"}})
    comics = {
        Path("cover-year.cbz"): _entry(
            start_year=2011,
            cover=date(2016, 1, 1),
            identifiers={"metron": {"key": "2"}},
        ),
        Path("other-volume.cbz"): _entry(
            start_year=2016, identifiers={"metron": {"key": "3"}}
        ),
    }
    result = match_comics(_list(entry), comics)

    assert result.missing == (0,)
    assert result.refused == ()


def test_the_same_number_in_another_volume_and_year_is_not_reported() -> None:
    comic = _entry(start_year=2016, cover=date(2016, 6, 1))
    result = match_comics(_list(_entry(start_year=2011)), {Path("b.cbz"): comic})

    assert result.missing == (0,)
    assert result.refused == ()


def test_a_found_entry_reports_nothing() -> None:
    comics = {
        Path("a.cbz"): _entry(start_year=2011),
        Path("b.cbz"): _entry(start_year=2016),
    }
    result = match_comics(_list(_entry(start_year=2011)), comics)

    assert result.found[0].paths == (Path("a.cbz"),)
    assert result.missing == ()
    assert result.refused == ()


def test_a_comic_another_entry_found_is_not_reported() -> None:
    comics = {Path("b.cbz"): _entry(start_year=2011)}
    result = match_comics(
        _list(_entry(start_year=2016), _entry(start_year=2011)), comics
    )

    assert result.missing == (0,)
    assert result.refused == ()


def test_refusals_are_sorted_by_position_then_path() -> None:
    comics = {
        Path("z.cbz"): _entry(start_year=2011),
        Path("a.cbz"): _entry(start_year=2011),
        Path("m.cbz"): _entry(start_year=2011, issue="2"),
    }
    result = match_comics(
        _list(_entry(start_year=2016, issue="2"), _entry(start_year=2016)), comics
    )

    assert result.refused == (
        Refused(0, Path("m.cbz"), RefusedReason.OTHER_VOLUME),
        Refused(1, Path("a.cbz"), RefusedReason.OTHER_VOLUME),
        Refused(1, Path("z.cbz"), RefusedReason.OTHER_VOLUME),
    )


# ------------------------- rl-core-3: the volume key is a loose key, like the
# cover-year key. A comic sharing only the volume key with an entry is judged
# with the entry's other loose matches, and combine links a volume-key pair by
# the cover-year key's rule.

_ZMEN_BARE = _entry(series="Z-Men", volume=1, cover=None)
_ZMEN_IDS = {"identifiers": {"metron": {"key": "63"}}}


def _comics(**rows: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    return {Path(f"{name}.cbz"): row for name, row in rows.items()}


def _by_name(found: Any) -> dict[str, tuple[FoundBy, bool]]:
    return {comic.path.stem: (comic.by, comic.ambiguous) for comic in found.comics}


def test_a_volume_only_entry_over_two_years_is_ambiguous() -> None:
    """Both were strong name matches, so write-arcs tagged both volumes."""
    reading_list = _list(_ZMEN_BARE)
    comics = _comics(zmen_1963=_ZMEN_1963, zmen_1991=_ZMEN_1991)

    result = match_comics(reading_list, comics)

    (found,) = result.found
    assert _by_name(found) == {
        "zmen_1963": (FoundBy.NAME, True),
        "zmen_1991": (FoundBy.NAME, True),
    }
    assert found.volumes == (1963, 1991)
    assert plan_arcs(reading_list, comics, result, "L") == ()


def test_a_volume_only_entry_over_one_year_is_not_ambiguous() -> None:
    comics = _comics(a=_ZMEN_1963, b=_ZMEN_1963)

    (found,) = match_comics(_list(_ZMEN_BARE), comics).found

    assert _by_name(found) == {"a": (FoundBy.NAME, False), "b": (FoundBy.NAME, False)}
    assert not found.ambiguous


def test_an_id_match_tells_the_volume_only_entry_its_year() -> None:
    """The id is of the 1963 comic, so the 1991 one is refused, not tagged."""
    entry = {**_ZMEN_BARE, **_ZMEN_IDS}
    comics = _comics(zmen_1963={**_ZMEN_1963, **_ZMEN_IDS}, zmen_1991=_ZMEN_1991)

    (found,) = match_comics(_list(entry), comics).found

    assert _by_name(found) == {"zmen_1963": (FoundBy.ID, False)}


def test_a_volume_only_entry_finds_its_exact_comic_alone() -> None:
    """As with the cover year: a comic of the entry's own signature rules."""
    comics = _comics(bare=_ZMEN_BARE, zmen_1963=_ZMEN_1963)

    (found,) = match_comics(_list(_ZMEN_BARE), comics).found

    assert _by_name(found) == {"bare": (FoundBy.NAME, False)}


def test_an_entry_with_a_start_year_still_finds_a_volume_only_comic() -> None:
    (found,) = match_comics(_list(_ZMEN_1991), _comics(bare=_ZMEN_BARE)).found
    assert _by_name(found) == {"bare": (FoundBy.NAME, False)}


def test_a_volume_only_row_beside_two_years_in_one_list_stays_alone() -> None:
    """It joined the first of the two volumes."""
    assert _groups(_list(_ZMEN_BARE), _list(_ZMEN_1963, _ZMEN_1991)) == [
        {(0, 0)},
        {(1, 0)},
        {(1, 1)},
    ]


def test_a_list_of_both_volumes_and_a_bare_row_combines_with_itself() -> None:
    rows = (_ZMEN_BARE, _ZMEN_1963, _ZMEN_1991)
    assert _groups(_list(*rows), _list(*rows)) == [{(0, r), (1, r)} for r in range(3)]
    assert compare(_list(*rows), _list(*rows)).verdict is Verdict.SAME


def test_a_volume_only_row_takes_its_exact_copy_over_a_year() -> None:
    groups = _groups(_list(_ZMEN_1963, _ZMEN_BARE), _list(_ZMEN_BARE))
    assert groups == [{(0, 0)}, {(0, 1), (1, 0)}]


def test_from_arcs_folds_no_volume_only_copy_it_cannot_place() -> None:
    rows = (_ZMEN_BARE, _ZMEN_1963, _ZMEN_1991)
    (reading_list,) = reading_lists_from_comics(
        {**row, "arcs": {"Saga": {}}} for row in rows
    )
    assert len(reading_list[ENTRIES_KEY]) == len(rows)


# The two cases the randomized match invariant found in the cover-year
# clauses, seeds 77 and 1167: a loose match is judged against every strong
# match, and against the other loose ones.

_ARDENT_COVER = date(2015, 1, 1)


def _ardent(start_year: int | None = None, volume: int | None = None, **ids: str):
    row = _entry(
        series="Ardent", start_year=start_year, volume=volume, cover=_ARDENT_COVER
    )
    if ids:
        row["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return row


def test_two_loose_comics_of_two_volumes_beside_an_id_match_are_ambiguous() -> None:
    """Seed 77: the v2 comic agreed with the id match, so v1 and v2 were both tagged."""
    comics = _comics(
        by_id=_ardent(2014, comicvine="2"), v2=_ardent(2014, 2), v1=_ardent(volume=1)
    )

    (found,) = match_comics(_list(_ardent(comicvine="2")), comics).found

    assert _by_name(found) == {
        "by_id": (FoundBy.ID, False),
        "v1": (FoundBy.NAME_YEAR, True),
        "v2": (FoundBy.NAME_YEAR, True),
    }


def test_a_loose_comic_of_another_volume_than_any_id_match_is_refused() -> None:
    """Seed 1167: it agreed with one id match and conflicted with another."""
    comics = _comics(
        y1999=_ardent(1999, metron="5"),
        v1=_ardent(volume=1, metron="5"),
        y2020_v1=_ardent(2020, 1),
    )

    (found,) = match_comics(_list(_ardent(metron="5")), comics).found

    assert _by_name(found) == {"v1": (FoundBy.ID, False), "y1999": (FoundBy.ID, False)}
