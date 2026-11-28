"""
An -i import file that cannot be read or parsed fails the comic.

It used to be logged as a warning (with a traceback for an unreadable
one) and skipped, and the run exited 0, writing the comic without the
metadata the user named. A file that parses but holds no usable tags is
still only a warning.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox import logger
from comicbox.box import Comicbox
from tests.cli.test_cli_export_extract_failures import _errors, _run_cli
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_GOOD = "<ComicInfo><Series>Imported</Series></ComicInfo>"
_UNPARSED = {
    "cut-short.xml": "<ComicInfo><Series>Foo",
    "words.txt": "just some words\n",
    "cut-short.json": '{"comicbox": {"series": {"name": "Foo"}}',
}
_NO_TAGS = {
    "empty.xml": "<ComicInfo></ComicInfo>",
    "other-root.xml": "<Something><Else>1</Else></Something>",
    "empty-mapping.yaml": "{}\n",
    "blank.txt": "",
}


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _comic(tmp_path: Path) -> Path:
    comic = tmp_path / "c.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, comic)
    return comic


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


@pytest.mark.parametrize("missing", ["missing.xml", "a-directory"])
def test_an_unreadable_import_fails_the_comic(tmp_path: Path, missing: str) -> None:
    comic = _comic(tmp_path)
    before = comic.read_bytes()
    bad = tmp_path / missing
    if missing == "a-directory":
        bad.mkdir()
    code, out = _run_cli("-w", "cix", "-i", str(bad), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out
    (error,) = _errors(out)
    assert f"-i {bad}: cannot read it:" in error
    assert "Traceback" not in out
    assert comic.read_bytes() == before


@pytest.mark.parametrize("name", sorted(_UNPARSED))
def test_an_unparsable_import_fails_the_comic(tmp_path: Path, name: str) -> None:
    comic = _comic(tmp_path)
    before = comic.read_bytes()
    bad = _write(tmp_path, name, _UNPARSED[name])
    code, out = _run_cli("-w", "cix", "-i", str(bad), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out
    (error,) = _errors(out)
    assert f"-i {bad}: not metadata comicbox can read" in error
    assert comic.read_bytes() == before


@pytest.mark.parametrize("name", sorted(_NO_TAGS))
def test_an_import_with_no_usable_tags_is_a_warning(tmp_path: Path, name: str) -> None:
    comic = _comic(tmp_path)
    empty = _write(tmp_path, name, _NO_TAGS[name])
    code, out = _run_cli("-p", "-i", str(empty), str(comic))
    assert code == 0
    assert not _errors(out)


def test_one_bad_import_of_several_fails_every_comic_and_writes_none(
    tmp_path: Path,
) -> None:
    """Every -i applies to every comic, so a bad one fails each, the good ones too."""
    first = _comic(tmp_path)
    second = tmp_path / "d.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, second)
    before = first.read_bytes()
    good = _write(tmp_path, "good.xml", _GOOD)
    bad = _write(tmp_path, "words.txt", _UNPARSED["words.txt"])
    code, out = _run_cli(
        "-w", "cix", "-i", str(good), "-i", str(bad), str(first), str(second)
    )
    assert code == 1
    assert "2 file(s) failed." in out
    assert len(_errors(out)) == 2
    assert first.read_bytes() == second.read_bytes() == before


def test_a_good_import_still_writes(tmp_path: Path) -> None:
    comic = _comic(tmp_path)
    good = _write(tmp_path, "good.xml", _GOOD)
    code, _ = _run_cli("-w", "cix", "-i", str(good), str(comic))
    assert code == 0
    with Comicbox(comic) as cb:
        assert cb.to_dict()["comicbox"]["series"]["name"] == "Imported"


def test_api_add_metadata_file_unreadable_raises_as_before(tmp_path: Path) -> None:
    with Comicbox() as cb, pytest.raises(FileNotFoundError):
        cb.add_metadata_file(tmp_path / "missing.xml")


def test_api_add_metadata_file_unparsable_warns_as_before(tmp_path: Path) -> None:
    """The library call is not -i: it still loads nothing and warns."""
    bad = _write(tmp_path, "words.txt", _UNPARSED["words.txt"])
    with Comicbox() as cb:
        cb.add_metadata_file(bad)
        assert cb.to_dict() == {}
