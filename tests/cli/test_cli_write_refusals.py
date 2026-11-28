"""
A read-only comic and a tar with a member named twice fail as one line.

ReadOnlyComicError and DuplicateMemberError subclassed UnwritableFormatError
("-w names no format this archive can hold"), so a caller catching that one
refusal caught two unrelated ones. They are siblings under ArchiveWriteError
now, and the CLI still lists each as an expected per-file failure.
"""

from __future__ import annotations

import io
import shutil
import sys
import tarfile
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from loguru import logger as loguru_logger

from comicbox import cli, logger
from comicbox.exceptions import (
    ArchiveWriteError,
    DuplicateMemberError,
    ReadOnlyComicError,
    UnwritableFormatError,
)
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Point loguru back at the real stdout; see test_cli_exit_code."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run_cli(*argv: str) -> tuple[int, str]:
    """
    Run `cli.main`, returning its exit code and the errors it logged.

    A string format makes loguru append any traceback to the message.
    """
    messages: list[str] = []
    handler = loguru_logger.add(messages.append, level="ERROR", format="{message}")
    old_stdout = sys.stdout
    code = 0
    try:
        sys.stdout = StringIO()
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.stdout = old_stdout
        loguru_logger.remove(handler)
    return code, "".join(messages)


@pytest.mark.parametrize("exc_class", [ReadOnlyComicError, DuplicateMemberError])
def test_refusals_are_siblings_of_unwritable_format(exc_class: type) -> None:
    """Each is its own ArchiveWriteError, not a kind of UnwritableFormatError."""
    assert exc_class.__bases__ == (ArchiveWriteError,)
    assert not issubclass(exc_class, UnwritableFormatError)


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_read_only_comic_is_one_line(tmp_path: Path, jobs: str) -> None:
    """Writing a 0444 CBZ logs the refusal with no traceback."""
    path = tmp_path / "comic.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, path)
    path.chmod(0o444)
    try:
        code, out = _run_cli("-j", jobs, "-m", "summary: New", "-w", "cr", str(path))
    finally:
        path.chmod(0o644)
    assert code == 1
    assert "read-only" in out
    assert "Traceback" not in out


def _tar_member(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_duplicate_member_is_one_line(tmp_path: Path, jobs: str) -> None:
    """Converting a tar that holds one name twice logs the refusal with no traceback."""
    cbt = tmp_path / "twice.cbt"
    with tarfile.open(cbt, "w") as archive:
        _tar_member(archive, "01.jpg", b"first")
        _tar_member(archive, "02.jpg", b"two")
        _tar_member(archive, "01.jpg", b"second")
    code, out = _run_cli("-j", jobs, "-z", str(cbt))
    assert code == 1
    assert "'01.jpg'" in out
    assert "Traceback" not in out
    assert not cbt.with_suffix(".cbz").exists()
