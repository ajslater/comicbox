"""
A write that publishes a new file keeps the comic's mode and is durable (A27).

A conversion builds its CBZ in a temporary file and replaces it into place;
an in-place PDF write saves to a temporary file too. Neither gave the new
file the original's mode, so a 0640 comic became 0644, and a conversion
never flushed its CBZ before ``delete_orig`` unlinked the source.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from comicbox.config import get_config
from comicbox.write import write_metadata
from tests.const import CIX_CBT_SOURCE_PATH, PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

_MODE = 0o640


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_conversion_keeps_the_comic_mode(tmp_path: Path) -> None:
    cbt = tmp_path / "issue.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    cbt.chmod(_MODE)

    result = write_metadata(cbt, {"title": "x"}, formats=["COMIC_INFO"])

    assert result.error is None
    cbz = tmp_path / "issue.cbz"
    assert result.final_path == cbz
    assert _mode(cbz) == _MODE


def test_a_pdf_write_keeps_the_comic_mode(tmp_path: Path) -> None:
    pdf = tmp_path / "issue.pdf"
    shutil.copy(PDF_SOURCE_PATH, pdf)
    pdf.chmod(_MODE)

    result = write_metadata(pdf, {"title": "x"}, formats=["PDF"])

    assert result.error is None
    assert result.final_path == pdf
    assert _mode(pdf) == _MODE


def test_a_conversion_is_flushed_before_the_original_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under ``delete_orig``, the CBZ's bytes reach the disk first."""
    cbt = tmp_path / "issue.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    calls: list[tuple[str, int | str]] = []
    real_fsync: Callable[[int], None] = os.fsync
    real_unlink = Path.unlink

    def fsync(fd: int) -> None:
        calls.append(("fsync", os.fstat(fd).st_ino))
        real_fsync(fd)

    def unlink(self: Path, *, missing_ok: bool = False) -> None:
        calls.append(("unlink", self.name))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(Path, "unlink", unlink)
    config = get_config({"comicbox": {"general": {"delete_orig": True}}})

    result = write_metadata(
        cbt, {"title": "x"}, formats=["COMIC_INFO"], base_config=config
    )

    assert result.error is None
    assert result.final_path
    assert not cbt.exists()
    unlinked_at = calls.index(("unlink", cbt.name))
    # replace() keeps the inode, so the CBZ's is the temporary file's.
    assert ("fsync", result.final_path.stat().st_ino) in calls[:unlinked_at]


def test_a_saved_pdf_is_written_when_its_mode_cannot_be_put_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A27 follow-up: the PDF is already saved when its mode is restored.

    On a filesystem that refuses chmod (vfat, CIFS) the write was reported
    failed although the new PDF was on disk. Restoring is best-effort.
    """
    pdf = tmp_path / "issue.pdf"
    shutil.copy(PDF_SOURCE_PATH, pdf)
    before = pdf.read_bytes()

    def chmod(self: Path, *_args: Any, **_kwargs: Any) -> None:
        raise PermissionError(errno.EPERM, "Operation not permitted", str(self))

    monkeypatch.setattr(Path, "chmod", chmod)
    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        result = write_metadata(pdf, {"title": "x"}, formats=["PDF"])
    finally:
        logger.remove(handler)

    assert result.error is None
    assert result.written
    assert pdf.read_bytes() != before
    assert any(
        str(pdf) in message and "mode" in message and "not permitted" in message
        for message in messages
    )
