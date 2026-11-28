"""
"The same file" needs more than an inode number (D6, section 10).

B8 and the write claim took two paths with one device and inode for one file.
Where every file reports the same inode, as some network and FUSE
filesystems do, three of four comics were skipped as "same file as" the
first. Two paths are one file when they resolve to one real path, or share a
device and a non-zero inode and the file has more than one link.
"""

from __future__ import annotations

import os
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from comicbox.box.archive.write import file_key
from comicbox.readinglists.tagging import group_files
from comicbox.run import _same_files
from tests.const import CIX_CBT_SOURCE_PATH

_COMIC_SUFFIXES = (".cbz", ".cbt")


@pytest.fixture
def one_inode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every comic report inode 42 with one link, as a FUSE mount can."""
    real_stat = Path.stat

    def stat(self: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(self, *args, **kwargs)
        if self.suffix.lower() not in _COMIC_SUFFIXES:
            return result
        fields = list(result[:10])
        fields[1], fields[3] = 42, 1  # st_ino, st_nlink
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "stat", stat)


def _comics(tmp_path: Path, count: int = 4) -> list[Path]:
    paths = [tmp_path / f"comic-{index}.cbt" for index in range(count)]
    for path in paths:
        shutil.copy(CIX_CBT_SOURCE_PATH, path)
    return paths


@pytest.mark.usefixtures("one_inode")
def test_comics_sharing_one_inode_number_are_different_files(tmp_path: Path) -> None:
    paths = _comics(tmp_path)

    assert len({file_key(path) for path in paths}) == len(paths)
    assert _same_files(paths).same_as == {}
    assert set(group_files(paths, file_key)) == set(paths)


def test_hard_links_are_one_file(tmp_path: Path) -> None:
    first, _ = _comics(tmp_path, 2)
    second_name = tmp_path / "hard-link.cbt"
    os.link(first, second_name)

    assert file_key(first) == file_key(second_name)
    assert _same_files([first, second_name]).same_as == {second_name: first}


def test_a_symlink_and_its_file_are_one_file(tmp_path: Path) -> None:
    (real,) = _comics(tmp_path, 1)
    link = tmp_path / "link.cbt"
    link.symlink_to(real)

    assert file_key(real) == file_key(link)
    assert _same_files([link, real]).same_as == {link: real}


def test_two_spellings_of_one_name_on_a_case_insensitive_disk_are_one_file(
    tmp_path: Path,
) -> None:
    """D12: D6 made Comic.cbt and comic.cbt two files there."""
    path = tmp_path / "Comic.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, path)
    other_spelling = tmp_path / "comic.cbt"
    if not other_spelling.exists():
        pytest.skip("this disk is case-sensitive")

    assert file_key(path) == file_key(other_spelling)
    assert _same_files([path, other_spelling]).same_as == {other_spelling: path}


def test_the_nfc_and_nfd_spellings_of_one_name_are_one_file(tmp_path: Path) -> None:
    """E5: D6 made them two files; they were one at fa457a6."""
    composed = tmp_path / unicodedata.normalize("NFC", "Café.cbt")
    shutil.copy(CIX_CBT_SOURCE_PATH, composed)
    decomposed = tmp_path / unicodedata.normalize("NFD", "Café.cbt")
    if not decomposed.exists():
        pytest.skip("this disk does not normalize names")

    assert file_key(composed) == file_key(decomposed)
    assert _same_files([composed, decomposed]).same_as == {decomposed: composed}


def test_an_inode_of_0_is_never_trusted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E7: a filesystem that reports inode 0, with links, made every comic one."""
    paths = _comics(tmp_path, 3)
    real_stat = Path.stat

    def stat(self: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(self, *args, **kwargs)
        if self.suffix.lower() not in _COMIC_SUFFIXES:
            return result
        fields = list(result[:10])
        fields[1], fields[3] = 0, 2  # st_ino, st_nlink
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "stat", stat)

    assert len({file_key(path) for path in paths}) == len(paths)
    assert _same_files(paths).same_as == {}


def test_a_missing_name_is_keyed_by_its_spelling(tmp_path: Path) -> None:
    """
    A7 follow-up: run-wide claim maps key a new file by its spelling.

    ``bulk_write``'s preflight and ``rl``'s one-per-destination check key
    destinations with ``file_key``. Folded there, ``issue.cbz`` and
    ``ISSUE.cbz``, two files on a case-sensitive disk, refused a valid
    sequential batch. Only the in-flight claim folds a new name.
    """
    assert file_key(tmp_path / "issue.cbz") != file_key(tmp_path / "ISSUE.cbz")
    assert file_key(tmp_path / "a" / "x.cbz") != file_key(tmp_path / "A" / "x.cbz")
