"""
Sniffing an unlabelled source never reads arbitrary text as a filename.

A source with no stated format is tried against each format it accepts.
The filename format accepts any string, so text that no tag format
reads, such as JSON without the ``comicbox`` root, was parsed as a comic
filename and its punctuation became the series and title.
"""

from __future__ import annotations

import shutil
import sys
from io import StringIO
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ROOTLESS_JSON = '{"series": {"name": "Foo"}, "issue": "7"}'


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run_cli(*argv: str) -> int:
    old_stdout = sys.stdout
    code = 0
    try:
        sys.stdout = StringIO()
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.stdout = old_stdout
    return code


def _series_title(path: Path) -> tuple:
    with Comicbox(path) as cb:
        md = cb.to_dict()["comicbox"]
    return md.get("series"), md.get("title"), md.get("stories")


def test_rootless_import_leaves_tags_unchanged(tmp_path: Path) -> None:
    """`-i meta.json -w cix` with JSON no format reads writes no junk."""
    comic = tmp_path / "imp.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, comic)
    meta = tmp_path / "meta.json"
    meta.write_text(_ROOTLESS_JSON)
    before = _series_title(comic)

    _run_cli("-i", str(meta), "-w", "cix", str(comic))

    assert _series_title(comic) == before


def test_unlabelled_api_string_is_not_a_filename() -> None:
    """A YAML string without the wrapper sets no series named `series`."""
    with Comicbox(metadata="series: Foo") as cb:
        md = cb.to_dict()
    assert md.get("comicbox", {}).get("series") is None
    assert md.get("comicbox", {}).get("title") is None


def test_explicit_filename_format_still_parses() -> None:
    """A string labelled as a filename is still read as one."""
    with Comicbox(
        metadata="Captain Science #002 (1951).cbz", fmt=MetadataFormats.FILENAME
    ) as cb:
        md = cb.to_dict()["comicbox"]
    assert md["series"]["name"] == "Captain Science"
    assert md["issue"]["name"] == "002"


def test_unknown_named_import_reads_its_real_format(tmp_path: Path) -> None:
    """ComicInfo XML imported under a name no format claims is read as XML."""
    comic = tmp_path / "imp.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, comic)
    meta = tmp_path / "tags.xml"
    meta.write_text(
        "<ComicInfo><Series>Bladehawk</Series><Number>3</Number></ComicInfo>"
    )
    with Comicbox(comic) as cb:
        cb.add_metadata_file(meta)
        md = cb.to_dict()["comicbox"]
    assert md["series"]["name"] == "Bladehawk"
    assert md["issue"]["name"] == "3"


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Capture the WARNING messages a library load logs."""
    from loguru import logger as loguru_logger

    captured: list[str] = []
    handler_id = loguru_logger.add(
        lambda m: captured.append(m.record["message"]), level="WARNING"
    )
    try:
        yield captured
    finally:
        loguru_logger.remove(handler_id)


def test_library_import_of_the_filename_export_parses(tmp_path: Path) -> None:
    """`add_metadata_file` names a format by file name, as `-i` does."""
    meta = tmp_path / "comicbox-filename.txt"
    meta.write_text("Captain Science #002 (1951).cbz")
    with Comicbox() as cb:
        cb.add_metadata_file(meta)
        md = cb.to_dict()["comicbox"]
    assert md["series"]["name"] == "Captain Science"


def test_an_unreadable_import_warns_once(tmp_path: Path, warnings: list[str]) -> None:
    """Formats that do not fit drop everything: that is no news."""
    meta = tmp_path / "notes.txt"
    meta.write_text("just some text\n")
    with Comicbox() as cb:
        cb.add_metadata_file(meta)
        assert cb.to_dict() == {}
    assert len(warnings) == 1
    assert "Unable to load" in warnings[0]


def test_the_chosen_format_still_warns_of_its_drops(
    tmp_path: Path, warnings: list[str]
) -> None:
    meta = tmp_path / "meta.json"
    meta.write_text('{"comicbox": {"series": {"name": "Foo"}, "page_count": "many"}}')
    with Comicbox() as cb:
        cb.add_metadata_file(meta)
        md = cb.to_dict()["comicbox"]
    assert md["series"]["name"] == "Foo"
    assert any("Dropped invalid metadata" in w and "page_count" in w for w in warnings)
