"""Unit tests for archive corruption and mislabeled-extension error paths."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.exceptions import ComicboxError, UnsupportedArchiveTypeError
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path


def test_non_archive_bytes_with_cbz_extension_raises(tmp_path: Path) -> None:
    """A .cbz of non-archive bytes fails detection at construction."""
    garbage = tmp_path / "garbage.cbz"
    garbage.write_bytes(b"this is not an archive at all " * 100)
    with pytest.raises(UnsupportedArchiveTypeError):
        Comicbox(garbage)


def test_non_archive_bytes_catchable_as_comicbox_error(tmp_path: Path) -> None:
    """The detection failure is catchable via the ComicboxError base."""
    garbage = tmp_path / "garbage.cbz"
    garbage.write_bytes(b"\x00\x01\x02\x03 nope " * 64)
    with pytest.raises(ComicboxError):
        Comicbox(garbage)


def test_empty_file_with_cbz_extension_raises(tmp_path: Path) -> None:
    """A zero-byte .cbz matches no archive detector."""
    empty = tmp_path / "empty.cbz"
    empty.touch()
    with pytest.raises(UnsupportedArchiveTypeError):
        Comicbox(empty)


def test_zip_misnamed_cbr_opens_as_cbz(tmp_path: Path) -> None:
    """
    A real zip misnamed .cbr still opens as a CBZ.

    Detection is content-based; the extension is only a priority hint.
    The .cbr hint tries rar first, fails, then falls through to the full
    detection order and identifies the zip.
    """
    mislabeled = tmp_path / "mislabeled.cbr"
    shutil.copy(CIX_CBZ_SOURCE_PATH, mislabeled)
    with Comicbox(mislabeled) as cb:
        assert cb.get_file_type() == "CBZ"
        assert cb.namelist()


def test_truncated_cbz_raises_unsupported_at_construction(tmp_path: Path) -> None:
    """
    A truncated CBZ raises UnsupportedArchiveTypeError from construction.

    Truncating to half size destroys the zip end-of-central-directory
    record at the tail of the file, so content-based detection no longer
    recognizes it as a zip (or anything else) and Comicbox() itself
    raises — to_dict() is never reachable, so corruption can never
    silently return an empty-success metadata dict.
    """
    truncated = tmp_path / "truncated.cbz"
    data = CIX_CBZ_SOURCE_PATH.read_bytes()
    truncated.write_bytes(data[: len(data) // 2])
    with pytest.raises(UnsupportedArchiveTypeError):
        Comicbox(truncated)


def test_truncated_cbz_failure_is_a_comicbox_error(tmp_path: Path) -> None:
    """The truncation failure is catchable via the ComicboxError base."""
    truncated = tmp_path / "truncated.cbz"
    data = CIX_CBZ_SOURCE_PATH.read_bytes()
    truncated.write_bytes(data[: len(data) // 2])
    with pytest.raises(ComicboxError):
        Comicbox(truncated)


def test_directory_path_raises_is_a_directory(tmp_path: Path) -> None:
    """A directory path is rejected with IsADirectoryError."""
    with pytest.raises(IsADirectoryError):
        Comicbox(tmp_path)


def test_nonexistent_path_raises_file_not_found(tmp_path: Path) -> None:
    """A nonexistent path is rejected with FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Comicbox(tmp_path / "does-not-exist.cbz")
