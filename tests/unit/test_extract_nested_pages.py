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


def test_the_index_is_padded_to_the_page_count(tmp_path: Path) -> None:
    """Ten pages: two digits, as comicbox pads a PDF's page names."""
    members = {
        f"{folder}/{n:02}.jpg": f"{folder}{n}".encode()
        for folder in "ab"
        for n in range(5)
    }
    extracted = _extract(_comic(tmp_path, members), tmp_path / "out")
    assert sorted(extracted) == [
        "00.jpg",
        "01.jpg",
        "02.jpg",
        "03.jpg",
        "04.jpg",
        "05-00.jpg",
        "06-01.jpg",
        "07-02.jpg",
        "08-03.jpg",
        "09-04.jpg",
    ]
    assert extracted["05-00.jpg"] == b"b0"


def test_the_names_are_the_same_every_run(tmp_path: Path) -> None:
    comic = _comic(tmp_path, _NESTED)
    assert _extract(comic, tmp_path / "one") == _extract(comic, tmp_path / "two")


def test_a_real_page_named_like_a_renamed_one_keeps_its_name(tmp_path: Path) -> None:
    """`b/01.jpg` cannot take `2-01.jpg`, a real page's name: it prefixes again."""
    members = {"a/01.jpg": b"a01", "a/2-01.jpg": b"a2-01", "b/01.jpg": b"b01"}
    extracted = _extract(_comic(tmp_path, members), tmp_path / "out")
    assert extracted == {"01.jpg": b"a01", "2-01.jpg": b"a2-01", "2-2-01.jpg": b"b01"}


def test_a_later_real_page_keeps_its_name_too(tmp_path: Path) -> None:
    """Names are decided before the first write, so `c/1-01.jpg` keeps its own."""
    members = {"a/01.jpg": b"a", "b/01.jpg": b"b", "c/1-01.jpg": b"c"}
    extracted = _extract(_comic(tmp_path, members), tmp_path / "out")
    assert extracted == {"01.jpg": b"a", "1-1-01.jpg": b"b", "1-01.jpg": b"c"}
