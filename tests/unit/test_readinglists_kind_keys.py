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
)
from comicbox.readinglists.identity import variant_keys
from comicbox.readinglists.match import FoundBy, match_comics

_COVER = date(2011, 11, 1)


def _entry(
    *,
    series: str = "Batman",
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
    return {"name": "Batman", "ordered": True, ENTRIES_KEY: list(entries)}


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
_XMEN_1963 = _entry(series="X-Men", start_year=1963, volume=1, cover=None)
_XMEN_1991 = _entry(series="X-Men", start_year=1991, volume=1, cover=None)


# ------------------------------------------------------------------ the keys


def test_an_entry_has_a_year_key_then_a_volume_key() -> None:
    assert _name_keys(_2011_V2) == [
        ("name", "batman", "year", 2011, Decimal(1), ""),
        ("name", "batman", "volume", 2, Decimal(1), ""),
    ]


def test_volume_2_is_not_year_2() -> None:
    assert not set(_name_keys(_V2)) & set(_name_keys(_entry(start_year=2)))


def test_a_year_like_volume_is_a_year_key() -> None:
    assert _name_keys(_entry(volume=2011)) == _name_keys(_entry(start_year=2011))


def test_variant_keys_keep_both_kinds_for_each_name() -> None:
    entry = _entry(series="The Batman (2011)", start_year=2011, volume=2)
    assert variant_keys(entry) == tuple(
        ("name", name, kind, value, Decimal(1), "")
        for name in ("the batman 2011", "the batman", "batman 2011")
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
    comics = {Path("1963.cbz"): _XMEN_1963, Path("1991.cbz"): _XMEN_1991}

    (found,) = match_comics(_list(_XMEN_1991), comics).found

    assert found.paths == (Path("1991.cbz"),)
    assert match_comics(_list(_XMEN_1991), {Path("a.cbz"): _XMEN_1963}).missing == (0,)


def test_a_year_like_volume_and_a_start_year_still_meet() -> None:
    result = match_comics(_list(_entry(volume=2011)), {Path("b.cbz"): _2011_V2})
    assert result.found[0].paths == (Path("b.cbz"),)


def test_a_variant_on_the_volume_key_of_another_year_is_refused() -> None:
    entry = _entry(series="X-Men (Vol. 1)", start_year=1991, volume=1, cover=None)
    assert match_comics(_list(entry), {Path("a.cbz"): _XMEN_1963}).missing == (0,)


# ------------------------------------------------------- combine and compare


def test_a_volume_only_row_joins_the_row_with_a_start_year() -> None:
    assert _groups(_list(_V2), _list(_2011_V2)) == [{(0, 0), (1, 0)}]


def test_two_volumes_of_one_name_stay_apart() -> None:
    assert _groups(_list(_XMEN_1963), _list(_XMEN_1991)) == [{(0, 0)}, {(1, 0)}]


def test_a_volume_only_row_does_not_carry_two_years_into_one_group() -> None:
    bare_v1 = _entry(series="X-Men", volume=1, cover=None)
    groups = _groups(_list(bare_v1), _list(_XMEN_1963), _list(_XMEN_1991))
    assert groups == [{(0, 0), (1, 0)}, {(2, 0)}]


def test_compare_keeps_two_volumes_apart() -> None:
    assert compare(_list(_XMEN_1963), _list(_XMEN_1991)).verdict is Verdict.UNRELATED
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
