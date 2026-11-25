"""
Fixtures shared by the ``comicbox rl`` modules.

Every comic is generated under ``tmp_path``: ``write-arcs`` changes comics,
so no test points it at anything else. A module opts into
``restore_cli_state`` with ``pytestmark``.
"""

from __future__ import annotations

import signal
from typing import TYPE_CHECKING

import pytest

from comicbox import logger
from tests.util.comics import make_comic
from tests.util.readinglist_cli import write_list

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# A ComicInfo.xml with a raw "&", which no XML parser reads.
_BROKEN_CIX = (
    "<ComicInfo><Series>Bladehawk & Rook</Series><Number>1</Number></ComicInfo>"
)


@pytest.fixture
def restore_cli_state() -> Iterator[None]:
    """Restore logging, and Ctrl-C, which a cancelled command leaves ignored."""
    handler = signal.getsignal(signal.SIGINT)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, handler)
        logger._initialized_key = None
        logger.init_logging()


@pytest.fixture
def reading_list(tmp_path: Path) -> Path:
    return write_list(tmp_path / "crimson-tide.yaml")


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Two of the list's issues, one by a variant name, and one it lacks."""
    directory = tmp_path / "comics"
    make_comic(
        directory / "cw1.cbz", series="Crimson Tide", number="1", start_year=2006
    )
    make_comic(
        directory / "asm532.cbz",
        series="The Amazing Snail-Man",
        number="532",
        start_year=1963,
    )
    make_comic(directory / "other.cbz", series="Sonnet", number="1", start_year=2012)
    return directory


@pytest.fixture
def unreadable(tmp_path: Path) -> Path:
    """Make a comic its file name matches, with a ComicInfo.xml no parser reads."""
    return make_comic(
        tmp_path / "comics" / "Bladehawk & Rook v2009 001 (2009).cbz",
        formats=(),
        files={"ComicInfo.xml": _BROKEN_CIX},
        series="unused",
        number="1",
    )


@pytest.fixture
def bladehawk_list(tmp_path: Path) -> Path:
    path = tmp_path / "bladehawk.yaml"
    path.write_text(
        "reading_list:\n  name: Bladehawk Reborn\n  entries:\n"
        "    - series: {name: Bladehawk & Rook}\n"
        "      volume: {number: 2009}\n"
        "      issue: {name: '1'}\n"
    )
    return path


@pytest.fixture
def captain_list(tmp_path: Path) -> Path:
    path = tmp_path / "captain.yaml"
    path.write_text(
        "reading_list:\n  name: Captain Arc\n  entries:\n"
        "    - series: {name: Captain Science}\n"
        "      volume: {number: 1950}\n"
        "      issue: {name: '1'}\n"
    )
    return path
