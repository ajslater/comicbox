"""
A failed export or extraction fails its file.

Each used to be logged and swallowed inside the box, so the Runner never
counted it and the run exited 0: a missing destination or a full disk
looked like success to a script.
"""

from __future__ import annotations

import shutil
import sys
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger as loguru_logger

from comicbox import cli, logger
from comicbox.box import Comicbox
from comicbox.exceptions import ExportError
from comicbox.formats import MetadataFormats
from tests.const import CIX_CBZ_SOURCE_PATH, PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _errors(out: str) -> list[str]:
    return [line for line in out.splitlines() if "| ERROR " in line]


def _run_cli(*argv: str) -> tuple[int, str]:
    """Run the CLI, its log bound to the returned stdout whatever ran before."""
    logger._initialized_key = None
    old_stdout = sys.stdout
    buf = StringIO()
    code = 0
    try:
        sys.stdout = buf
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        # The sink is enqueued: drain it before the buffer is read.
        loguru_logger.complete()
        sys.stdout = old_stdout
    return code, buf.getvalue()


def _comic(tmp_path: Path, source: Path = CIX_CBZ_SOURCE_PATH) -> Path:
    comic = tmp_path / f"c{source.suffix}"
    shutil.copy(source, comic)
    return comic


def _out_dir(tmp_path: Path) -> Path:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return out_dir


@pytest.fixture
def full_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every page write fails as on a full disk, whoever runs the test."""

    def _fail(self: Path, _data: bytes) -> int:
        reason = f"No space left on device: {self}"
        raise OSError(28, reason)

    monkeypatch.setattr(Path, "write_bytes", _fail)


def test_export_to_a_missing_directory_fails_the_file(tmp_path: Path) -> None:
    comic = _comic(tmp_path)
    code, out = _run_cli("-e", "cix", "-d", str(tmp_path / "nope"), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out
    (error,) = _errors(out)
    assert "Could not export ComicInfo.xml" in error


def test_export_tries_every_format_before_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One format failing does not stop the others being exported."""
    comic = _comic(tmp_path)
    out_dir = _out_dir(tmp_path)
    original = Path.open

    def _open(self: Path, *args, **kwargs):
        if self.name == "ComicInfo.xml":
            reason = f"No space left on device: {self}"
            raise OSError(28, reason)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _open)
    code, out = _run_cli("-e", "cix,json", "-d", str(out_dir), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out
    (error,) = _errors(out)
    assert "Could not export ComicInfo.xml" in error
    assert (out_dir / "comicbox.json").exists()


def test_api_to_file_raises_export_error(tmp_path: Path) -> None:
    with Comicbox(CIX_CBZ_SOURCE_PATH) as cb, pytest.raises(ExportError):
        cb.to_file(tmp_path / "nope", MetadataFormats.COMIC_INFO)


@pytest.mark.usefixtures("full_disk")
def test_extract_pages_failure_fails_the_file(tmp_path: Path) -> None:
    comic = _comic(tmp_path)
    code, out = _run_cli("-x", "0:2", "-d", str(_out_dir(tmp_path)), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out


@pytest.mark.usefixtures("full_disk")
def test_extract_covers_failure_fails_the_file(tmp_path: Path) -> None:
    comic = _comic(tmp_path)
    code, out = _run_cli("-X", "-d", str(_out_dir(tmp_path)), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out


@pytest.mark.usefixtures("full_disk")
def test_extract_pdf_range_failure_fails_the_file(tmp_path: Path) -> None:
    comic = _comic(tmp_path, PDF_SOURCE_PATH)
    code, out = _run_cli("-x", "0:1", "-d", str(_out_dir(tmp_path)), str(comic))
    assert code == 1
    assert "1 file(s) failed." in out


def test_extract_pages_to_a_good_directory_still_succeeds(tmp_path: Path) -> None:
    comic = _comic(tmp_path)
    out_dir = _out_dir(tmp_path)
    code, _ = _run_cli("-x", "0:2", "-d", str(out_dir), str(comic))
    assert code == 0
    assert len(list(out_dir.iterdir())) == 3
