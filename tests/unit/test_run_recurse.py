"""Unit tests for the Runner's recursive directory walk."""

from __future__ import annotations

from typing import TYPE_CHECKING

from comicbox.enums.comicbox import FileTypeEnum
from comicbox.run import Runner

if TYPE_CHECKING:
    from pathlib import Path


def _runner(path: Path) -> Runner:
    return Runner({"comicbox": {"general": {"recurse": True}, "paths": (str(path),)}})


def test_recurse_finds_every_supported_file_type(tmp_path: Path) -> None:
    """
    --recurse walks all five archive types, .cb7 included.

    The suffix set was written out by hand and .cb7 was left off it, so a
    recursive run silently skipped every 7z comic in a library — no error,
    no log line, just files that were never processed.
    """
    for file_type in FileTypeEnum:
        (tmp_path / f"comic.{file_type.value.lower()}").write_bytes(b"")

    found = {path.suffix for path in _runner(tmp_path)._iter_recurse(tmp_path)}

    assert found == {f".{file_type.value.lower()}" for file_type in FileTypeEnum}
    assert ".cb7" in found


def test_recurse_ignores_unsupported_suffixes(tmp_path: Path) -> None:
    """Deriving the set from the enum must not widen the walk to everything."""
    (tmp_path / "comic.cbz").write_bytes(b"")
    for name in ("cover.jpg", "notes.txt", "comicinfo.xml", "noext"):
        (tmp_path / name).write_bytes(b"")

    found = [path.name for path in _runner(tmp_path)._iter_recurse(tmp_path)]

    assert found == ["comic.cbz"]


def test_recurse_matches_a_suffix_case_insensitively(tmp_path: Path) -> None:
    """Libraries carry uppercase suffixes; the walk lowercases before matching."""
    (tmp_path / "SHOUTING.CB7").write_bytes(b"")

    found = [path.name for path in _runner(tmp_path)._iter_recurse(tmp_path)]

    assert found == ["SHOUTING.CB7"]


def test_recurse_descends_into_subdirectories(tmp_path: Path) -> None:
    """The walk is recursive and yields in sorted order."""
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "second.cb7").write_bytes(b"")
    (tmp_path / "a.cbz").write_bytes(b"")

    found = [path.name for path in _runner(tmp_path)._iter_recurse(tmp_path)]

    assert found == ["a.cbz", "second.cb7"]
