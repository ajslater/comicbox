"""Unit tests for archive corruption and mislabeled-extension error paths."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.exceptions import ComicboxError, UnsupportedArchiveTypeError
from tests.const import CB7_SOURCE_PATH, CIX_CBZ_SOURCE_PATH, PDF_SOURCE_PATH

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


@pytest.mark.parametrize(
    ("source_path", "expected_type"),
    [(PDF_SOURCE_PATH, "PDF"), (CB7_SOURCE_PATH, "CB7")],
)
def test_zip_tail_cannot_shadow_leading_magic_format(
    tmp_path: Path, source_path: Path, expected_type: str
) -> None:
    """
    A pdf or 7z with zip data appended detects as its leading-magic type.

    is_zipfile only scans the tail for an end-of-central-directory record,
    so such a polyglot matches the zip detector too. The strict zip
    detector requires zip leading magic, so with no extension hint the
    real format still wins despite zip running first in the full order.
    """
    polyglot = tmp_path / "no_extension_hint"
    polyglot.write_bytes(source_path.read_bytes() + CIX_CBZ_SOURCE_PATH.read_bytes())
    with Comicbox(polyglot) as cb:
        assert cb.get_file_type() == expected_type


def test_zip_with_prepended_data_still_opens_as_cbz(tmp_path: Path) -> None:
    """
    A zip that starts with other data is still detected, last.

    The zip format allows prepended data (self-extractors). The strict
    leading-magic zip detector rejects it, no other format matches, and
    the loose terminal zip detector accepts it.
    """
    prepended = tmp_path / "self_extracting.cbz"
    prepended.write_bytes(
        b"#!/bin/sh\necho fake sfx stub\n" + CIX_CBZ_SOURCE_PATH.read_bytes()
    )
    with Comicbox(prepended) as cb:
        assert cb.get_file_type() == "CBZ"
        assert cb.namelist()


def test_directory_path_raises_is_a_directory(tmp_path: Path) -> None:
    """A directory path is rejected with IsADirectoryError."""
    with pytest.raises(IsADirectoryError):
        Comicbox(tmp_path)


def test_nonexistent_path_raises_file_not_found(tmp_path: Path) -> None:
    """A nonexistent path is rejected with FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Comicbox(tmp_path / "does-not-exist.cbz")
