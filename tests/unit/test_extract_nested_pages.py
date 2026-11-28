"""
Pages that share a name in two folders are all extracted.

Extraction names each page by its base name, so an archive laid out by
chapter (``ch1/01.jpg``, ``ch2/01.jpg``) wrote every chapter's pages to
the same names, and the log still said every page was saved.
"""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

from comicbox.box import Comicbox

if TYPE_CHECKING:
    from pathlib import Path

_NESTED = {
    "ch1/01.jpg": b"ch1-01",
    "ch1/02.jpg": b"ch1-02",
    "ch2/01.jpg": b"ch2-01",
    "ch2/02.jpg": b"ch2-02",
}


def _comic(tmp_path: Path, members: dict[str, bytes]) -> Path:
    path = tmp_path / "nested.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def _extract(comic: Path, out: Path) -> dict[str, bytes]:
    out.mkdir()
    with Comicbox(comic) as cb:
        cb.extract_pages(0, None, out)
    return {path.name: path.read_bytes() for path in out.iterdir()}


def test_pages_sharing_a_name_are_all_saved(tmp_path: Path) -> None:
    extracted = _extract(_comic(tmp_path, _NESTED), tmp_path / "out")
    assert sorted(extracted.values()) == sorted(_NESTED.values())


def test_the_first_of_a_name_keeps_it(tmp_path: Path) -> None:
    """Only a repeat is renamed, by its page index."""
    extracted = _extract(_comic(tmp_path, _NESTED), tmp_path / "out")
    assert extracted == {
        "01.jpg": b"ch1-01",
        "02.jpg": b"ch1-02",
        "2-01.jpg": b"ch2-01",
        "3-02.jpg": b"ch2-02",
    }


def test_names_differing_only_in_case_do_not_collide(tmp_path: Path) -> None:
    """One file on a case-insensitive disk, so a repeat on every disk."""
    members = {"a/01.jpg": b"a", "b/01.JPG": b"b"}
    extracted = _extract(_comic(tmp_path, members), tmp_path / "out")
    assert sorted(extracted.values()) == [b"a", b"b"]


def test_flat_archives_keep_their_names(tmp_path: Path) -> None:
    members = {"01.jpg": b"1", "02.jpg": b"2"}
    extracted = _extract(_comic(tmp_path, members), tmp_path / "out")
    assert extracted == {"01.jpg": b"1", "02.jpg": b"2"}
