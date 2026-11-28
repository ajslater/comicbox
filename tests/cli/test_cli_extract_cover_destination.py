"""
`-X -d FILE` never overwrites a comic, nor writes two covers to one file.

A file destination took the cover whatever it was: a mistyped `-d`
naming a comic replaced that comic with a JPEG and the run exited 0, and
with several input comics every cover landed on the one file.
"""

from __future__ import annotations

import shutil
import sys
from io import StringIO
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from tests.const import CIX_CBZ_SOURCE_PATH, PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_JPEG_MAGIC = b"\xff\xd8\xff"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run_cli(*argv: str) -> tuple[int, str]:
    old_stdout = sys.stdout
    buf = StringIO()
    code = 0
    try:
        sys.stdout = buf
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.stdout = old_stdout
    return code, buf.getvalue()


def _two_comics(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a.cbz"
    b = tmp_path / "b.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, a)
    shutil.copy(CIX_CBZ_SOURCE_PATH, b)
    return a, b


def test_a_comic_destination_is_refused(tmp_path: Path) -> None:
    """The regression: `-X -d a.cbz b.cbz` left a.cbz a JPEG."""
    a, b = _two_comics(tmp_path)
    before = a.read_bytes()
    code, out = _run_cli("-X", "-d", str(a), str(b))
    assert a.read_bytes() == before
    assert code == 1
    assert "1 file(s) failed." in out


def test_a_comic_destination_is_refused_by_content(tmp_path: Path) -> None:
    """A PDF named like an image is still a comic."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    shutil.copy(PDF_SOURCE_PATH, dest)
    before = dest.read_bytes()
    code, _ = _run_cli("-X", "-d", str(dest), str(b))
    assert dest.read_bytes() == before
    assert code == 1


def test_a_comic_cannot_take_its_own_cover(tmp_path: Path) -> None:
    a, _ = _two_comics(tmp_path)
    before = a.read_bytes()
    code, _ = _run_cli("-X", "-d", str(a), str(a))
    assert a.read_bytes() == before
    assert code == 1


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_two_comics_to_one_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], jobs: str
) -> None:
    """Every cover would land on one file: refused before any is written."""
    a, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    code, _ = _run_cli("-j", jobs, "-X", "-d", str(dest), str(a), str(b))
    assert code == 2
    assert ": error: -X to one file takes one comic, 2 found" in capsys.readouterr().err
    assert not dest.exists()


def test_a_directory_of_two_comics_to_one_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    comics = tmp_path / "comics"
    comics.mkdir()
    _two_comics(comics)
    dest = tmp_path / "cover.jpg"
    code, _ = _run_cli("-r", "-X", "-d", str(dest), str(comics))
    assert code == 2
    assert "-X to one file takes one comic, 2 found" in capsys.readouterr().err
    assert not dest.exists()


def test_an_existing_image_destination_is_still_overwritten(tmp_path: Path) -> None:
    """A re-run refreshes cover.jpg: pinned, current behavior."""
    _, b = _two_comics(tmp_path)
    dest = tmp_path / "cover.jpg"
    dest.write_bytes(b"old cover")
    code, _ = _run_cli("-X", "-d", str(dest), str(b))
    assert code == 0
    assert dest.read_bytes().startswith(_JPEG_MAGIC)


def test_two_comics_to_a_directory_still_work(tmp_path: Path) -> None:
    a, b = _two_comics(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, _ = _run_cli("-X", "-d", str(out_dir), str(a), str(b))
    assert code == 0
    assert len(list(out_dir.iterdir())) == 1
