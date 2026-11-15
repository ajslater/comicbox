"""Reading lists and comics' arc tags."""

from __future__ import annotations

import shutil
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from comicbox.box import Comicbox
from comicbox.readinglists import (
    ENTRIES_KEY,
    arc_patch,
    entry_from_comic,
    reading_lists_from_comics,
)
from comicbox.write import write_metadata
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_COMIC = {
    "series": {
        "name": "Civil War",
        "start_year": 2006,
        "identifiers": {"comicvine": {"key": "18023"}},
        "summary": "Dropped from the entry.",
    },
    "volume": {"number": 2006, "issue_count": 7},
    "issue": {"name": "1", "number": Decimal(1)},
    "date": {"cover_date": date(2006, 7, 1), "year": 2006, "month": 7},
    "identifiers": {"comicvine": {"key": "105747"}},
    "title": "Dropped from the entry.",
}
_ENTRY = {
    "series": {
        "name": "Civil War",
        "start_year": 2006,
        "identifiers": {"comicvine": {"key": "18023"}},
    },
    "volume": {"number": 2006},
    "issue": {"name": "1", "number": Decimal(1)},
    "date": {"cover_date": date(2006, 7, 1), "year": 2006},
    "identifiers": {"comicvine": {"key": "105747"}},
}


def test_entry_from_comic_inner() -> None:
    assert entry_from_comic(_COMIC) == _ENTRY


def test_entry_from_comic_wrapped() -> None:
    assert entry_from_comic({"comicbox": _COMIC}) == _ENTRY


def _comic(issue: str, arcs: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "series": {"name": "Civil War", "start_year": 2006},
        "issue": {"name": issue},
        "arcs": arcs,
        **fields,
    }


def _issues(reading_list: dict[str, Any]) -> list[str]:
    return [entry["issue"]["name"] for entry in reading_list[ENTRIES_KEY]]


def test_numbered_arc_is_ordered() -> None:
    comics = [
        _comic("3", {"Civil War": {"number": 3}}),
        _comic("1", {"Civil War": {"number": 1}}),
        _comic("2", {"Civil War": {"number": 2}}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    assert reading_list["name"] == "Civil War"
    assert reading_list["list_type"] == "story"
    assert reading_list["ordered"] is True
    assert reading_list["sources"] == [{"kind": "tags"}]
    assert _issues(reading_list) == ["1", "2", "3"]


def test_unnumbered_arc_sorts_by_date() -> None:
    comics = [
        _comic("2", {"Civil War": {}}, date={"cover_date": date(2006, 8, 1)}),
        _comic("1", {"Civil War": {}}, date={"cover_date": date(2006, 7, 1)}),
        _comic("3", {"Civil War": {}}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    assert reading_list["ordered"] is False
    assert _issues(reading_list) == ["1", "2", "3"]


def test_partly_numbered_arc_is_unordered() -> None:
    comics = [
        _comic("2", {"Civil War": {}}),
        _comic("1", {"Civil War": {"number": 1}}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    assert reading_list["ordered"] is False
    assert _issues(reading_list) == ["1", "2"]


def test_repeated_numbers_are_unordered() -> None:
    comics = [
        _comic("2", {"Civil War": {"number": 1}}),
        _comic("1", {"Civil War": {"number": 1}}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    assert reading_list["ordered"] is False
    # Equal numbers fall back to series and issue.
    assert _issues(reading_list) == ["1", "2"]


def test_two_spellings_make_one_list() -> None:
    comics = [
        _comic("1", {"Civil War": {"number": 1}, "Road to Civil War": {"number": 9}}),
        _comic("2", {"CIVIL WAR": {"number": 2}}),
    ]
    lists = reading_lists_from_comics(comics)
    assert [reading_list["name"] for reading_list in lists] == [
        "Civil War",
        "Road to Civil War",
    ]
    assert _issues(lists[0]) == ["1", "2"]
    assert _issues(lists[1]) == ["1"]


def test_comics_without_arcs_make_no_lists() -> None:
    assert reading_lists_from_comics([{"series": {"name": "A"}}, {}]) == []


def _arc_ids(**ids: str) -> dict[str, Any]:
    return {"identifiers": {source: {"key": key} for source, key in ids.items()}}


def test_arc_ids_become_pointer_sources() -> None:
    comics = [
        _comic("1", {"Civil War": {"number": 1, **_arc_ids(comicvine="55766")}}),
        _comic("2", {"Civil War": {"number": 2, **_arc_ids(metron="17")}}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    assert reading_list["sources"] == [
        {"kind": "tags"},
        {"kind": "metron-arc", "key": "17"},
        {"kind": "comicvine-arc", "key": "55766"},
    ]


def test_disagreeing_arc_ids_most_common_wins() -> None:
    comics = [
        _comic("1", {"Civil War": _arc_ids(metron="9", comicvine="1")}),
        _comic("2", {"Civil War": _arc_ids(metron="17", comicvine="2")}),
        _comic("3", {"Civil War": _arc_ids(metron="17")}),
    ]
    (reading_list,) = reading_lists_from_comics(comics)
    # Metron: 17 twice beats 9 once. ComicVine: a tie goes to the first seen.
    assert reading_list["sources"][1:] == [
        {"kind": "metron-arc", "key": "17"},
        {"kind": "comicvine-arc", "key": "1"},
    ]


def test_arc_patch() -> None:
    assert arc_patch("Civil War", 3) == {"arcs": {"Civil War": {"number": 3}}}
    assert arc_patch("Civil War") == {"arcs": {"Civil War": {}}}


def test_arc_patch_adds_an_arc_and_keeps_the_others(tmp_path: Path) -> None:
    path = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, path)
    write_metadata(path, arc_patch("Road to Civil War", 9), formats=["comicbox_json"])
    result = write_metadata(path, arc_patch("Civil War", 1), formats=["comicbox_json"])
    assert result.error is None
    with Comicbox(path) as cb:
        arcs = cb.get_internal_metadata()["comicbox"]["arcs"]
    assert arcs["Civil War"] == {"number": 1}
    assert arcs["Road to Civil War"] == {"number": 9}
