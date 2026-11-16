"""
A PDF write replaces its tag files and no other attachment (B14).

pymupdf's ``embfile_del`` removes the right embedded file only when it is the
first. Comicbox used it on every tag file, in its own sorted order, so an
attachment stored before a tag file was left holding that tag file's bytes,
and a PDF with tag files out of that order failed the write and lost some.
On copies of tests/files, re-embedded in the order each test needs.
"""

from __future__ import annotations

import shutil
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pymupdf
import pytest

from comicbox.config import get_config
from comicbox.exceptions import UnsafePdfAttachmentError
from comicbox.write import write_metadata
from tests.const import CIX_PDF_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_CIX = "ComicInfo.xml"
_MI = "MetronInfo.xml"
_COMET = "CoMet.xml"
_OTHERS: dict[str, bytes] = {
    "notes.txt": b"the scanner's notes",
    "cover.png": b"\x89PNG not really",
}
_OLD_TAGS: dict[str, bytes] = {
    _MI: b"<?xml version='1.0'?><MetronInfo><Summary>Old</Summary></MetronInfo>",
    _COMET: b"<?xml version='1.0'?><comet><title>Old</title></comet>",
}


def _config(**dests: Any) -> Any:
    return get_config(Namespace(comicbox=Namespace(**dests)))


def _make_pdf(tmp_path: Path, order: Sequence[str]) -> Path:
    """Copy the ComicInfo PDF and embed these attachments, in this order."""
    path = tmp_path / "comic.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    with pymupdf.open(path) as doc:
        data = {_CIX: doc.embfile_get(_CIX), **_OTHERS, **_OLD_TAGS}
        while doc.embfile_names():
            # Only the first embedded file is ever removed rightly.
            doc.embfile_del(0)
        for name in order:
            doc.embfile_add(name, data[name])
        doc.saveIncr()
    return path


def _attachments(path: Path) -> dict[str, bytes]:
    with pymupdf.open(path) as doc:
        names = doc.embfile_names()
        assert len(names) == len(set(names)), names
        return {name: doc.embfile_get(name) for name in names}


def _page_count(path: Path) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


@pytest.mark.parametrize(
    "order",
    [
        ("notes.txt", _CIX),
        (_CIX, "notes.txt"),
        ("notes.txt", _CIX, "cover.png"),
        (_COMET, "notes.txt", _MI, "cover.png", _CIX),
    ],
)
def test_a_write_leaves_other_attachments_byte_for_byte(
    tmp_path: Path, order: tuple[str, ...]
) -> None:
    """``notes.txt`` stored first was left holding the old ComicInfo."""
    path = _make_pdf(tmp_path, order)
    pages = _page_count(path)

    result = write_metadata(path, {"summary": "New"}, formats=["COMIC_INFO"])

    assert result.written, result.error
    attachments = _attachments(path)
    others = {name: data for name, data in attachments.items() if name in _OTHERS}
    assert others == {name: _OTHERS[name] for name in order if name in _OTHERS}
    # -w cix removes the other tag files, as it does in a CBZ.
    assert sorted(attachments) == sorted([*others, _CIX])
    assert b"<Summary>New</Summary>" in attachments[_CIX]
    assert _page_count(path) == pages


@pytest.mark.parametrize(
    "order",
    [(_MI, _CIX, _COMET), (_COMET, _MI, _CIX), (_CIX, _COMET, _MI)],
)
def test_a_pdf_with_three_tag_files_is_written(
    tmp_path: Path, order: tuple[str, ...]
) -> None:
    """Out of comicbox's sorted order, the write failed and lost tag files."""
    path = _make_pdf(tmp_path, order)

    result = write_metadata(path, {"summary": "New"}, formats=["COMIC_INFO"])

    assert result.written, result.error
    attachments = _attachments(path)
    assert list(attachments) == [_CIX]
    assert b"<Summary>New</Summary>" in attachments[_CIX]


@pytest.mark.parametrize(
    "order",
    [(_COMET, "notes.txt", _MI, _CIX, "cover.png"), (_CIX, _MI, "notes.txt", _COMET)],
)
def test_keep_leaves_unread_tag_files_and_attachments_byte_for_byte(
    tmp_path: Path, order: tuple[str, ...]
) -> None:
    path = _make_pdf(tmp_path, order)
    before = _attachments(path)

    result = write_metadata(
        path,
        {"summary": "Again"},
        formats=["keep"],
        base_config=_config(**{"read.formats": ["cix"]}),
    )

    assert result.written, result.error
    after = _attachments(path)
    assert sorted(after) == sorted(order)
    assert {name: after[name] for name in order if name != _CIX} == {
        name: before[name] for name in order if name != _CIX
    }
    assert b"<Summary>Again</Summary>" in after[_CIX]


def test_delete_all_tags_leaves_other_attachments(tmp_path: Path) -> None:
    path = _make_pdf(tmp_path, (_MI, "notes.txt", _CIX, "cover.png", _COMET))

    result = write_metadata(
        path,
        {"summary": "Ignored"},
        formats=["COMIC_INFO"],
        base_config=_config(**{"write.delete_all_tags": True}),
    )

    assert result.written, result.error
    assert _attachments(path) == _OTHERS


def _rename_third_attachment(path: Path, old: str, new: str) -> None:
    """Give a PDF two attachments of one name, which pymupdf won't add."""
    with pymupdf.open(path) as doc:
        catalog = doc.pdf_catalog()
        _, names = doc.xref_get_key(catalog, "Names/EmbeddedFiles/Names")
        renamed = names.replace(f"({old})<<", f"({new})<<", 1)
        doc.xref_set_key(catalog, "Names/EmbeddedFiles/Names", renamed)
        doc.saveIncr()


@pytest.mark.parametrize("unsafe", ["page", "duplicate"])
def test_an_attachment_that_cannot_be_put_back_refuses_the_write(
    tmp_path: Path, unsafe: str
) -> None:
    """
    Refuse before anything changes.

    pdffile reads and removes an attachment named "1" as page 1, and
    pymupdf finds only the first of two attachments with one name.
    """
    path = tmp_path / "comic.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    with pymupdf.open(path) as doc:
        cix = doc.embfile_get(_CIX)
        doc.embfile_del(0)
        first = "1" if unsafe == "page" else "notes.txt"
        doc.embfile_add(first, b"stored first")
        doc.embfile_add(_CIX, cix)
        doc.embfile_add("later.txt", b"stored last")
        doc.saveIncr()
    if unsafe == "duplicate":
        _rename_third_attachment(path, "later.txt", "notes.txt")
    original = path.read_bytes()

    result = write_metadata(path, {"summary": "New"}, formats=["COMIC_INFO"])

    assert not result.written
    assert isinstance(result.error, UnsafePdfAttachmentError)
    assert repr(first) in str(result.error)
    assert path.read_bytes() == original


@pytest.mark.parametrize("unsafe", ["page", "duplicate"])
def test_converting_a_pdf_with_an_attachment_that_would_be_lost_is_refused(
    tmp_path: Path, unsafe: str
) -> None:
    """
    D8: an attachment named "1" was read as page 1.

    The CBZ had page 1 twice and no attachment. Refused before anything is
    written, as a PDF write is.
    """
    path = tmp_path / "comic.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    name = "1" if unsafe == "page" else "notes.txt"
    with pymupdf.open(path) as doc:
        doc.embfile_add(name, b"an attachment")
        doc.embfile_add("later.txt", b"stored last")
        doc.saveIncr()
    if unsafe == "duplicate":
        _rename_third_attachment(path, "later.txt", "notes.txt")
    original = path.read_bytes()

    result = write_metadata(
        path,
        {"summary": "New"},
        formats=["COMIC_INFO"],
        base_config=_config(**{"convert.cbz": True}),
    )

    assert not result.written
    assert isinstance(result.error, UnsafePdfAttachmentError)
    assert "convert it to a CBZ" in str(result.error)
    assert path.read_bytes() == original
    assert not path.with_suffix(".cbz").exists()
    assert {p.name for p in tmp_path.iterdir()} == {"comic.pdf"}
