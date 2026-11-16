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
