"""
ComicInfo keeps arc numbers when an arc has none.

StoryArcNumber is a list parallel to StoryArc. One arc without a number
used to fail the whole tag, so every arc lost its number.
"""

from __future__ import annotations

import shutil
import zipfile
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.write import write_metadata
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

# The fixture's own arcs: two StoryArcs and its Alternate series.
_FIXTURE_ARCS = {
    "Captain Arc": {"number": 4},
    "Other Arc": {"number": 2},
    "Captain Science Alternate": {"number": 1},
}


def _arcs(path: Path) -> dict:
    with Comicbox(path) as cb:
        return cb.get_internal_metadata()["comicbox"]["arcs"]


def _comic_info(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower() == "comicinfo.xml")
        return archive.read(name).decode()


@pytest.fixture
def comic(tmp_path: Path) -> Path:
    path = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, path)
    assert _arcs(path) == _FIXTURE_ARCS
    return path


@pytest.mark.parametrize("fmt", ["comic_info", "comicbox_json"])
def test_an_arc_without_a_number_keeps_the_others_numbers(
    comic: Path, fmt: str
) -> None:
    write_metadata(comic, {"arcs": {"New Arc": {}}}, formats=[fmt])
    assert _arcs(comic) == {**_FIXTURE_ARCS, "New Arc": {}}


@pytest.mark.parametrize("fmt", ["comic_info", "comicbox_json"])
def test_an_arc_with_a_number_joins_the_others(comic: Path, fmt: str) -> None:
    write_metadata(comic, {"arcs": {"New Arc": {"number": 7}}}, formats=[fmt])
    assert _arcs(comic) == {**_FIXTURE_ARCS, "New Arc": {"number": 7}}


def test_numbered_arcs_are_written_first(comic: Path) -> None:
    """The numbers are a clean prefix: no empty slots for unnumbered arcs."""
    write_metadata(comic, {"arcs": {"Aaa Unnumbered": {}}}, formats=["comic_info"])
    text = _comic_info(comic)
    assert (
        "<StoryArc>Captain Arc,Other Arc,Captain Science Alternate,Aaa Unnumbered"
        "</StoryArc>"
    ) in text
    assert "<StoryArcNumber>4,2,1</StoryArcNumber>" in text
