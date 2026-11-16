"""-w pdf writes a PDF's own metadata (B13), and what it writes reads back (B13b)."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pymupdf
import pytest

from comicbox.box import Comicbox
from comicbox.write import write_metadata
from tests.const import CIX_PDF_SOURCE_PATH, PDF_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_CIX = "ComicInfo.xml"
_NOTES = b"the scanner's notes"
_PATCH: dict[str, Any] = {
    "title": "New Title",
    "genres": ["Horror"],
    "tags": ["t1"],
    "credits": {"Jane Writer": {"roles": {"Writer": {}}}},
    "scan_info": "Scanner X",
    "tagger": "Tagger Y",
    "updated_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
}


def _pages(doc: pymupdf.Document) -> list[str]:
    return [hashlib.sha256(page.get_pixmap().samples).hexdigest() for page in doc]


def test_w_pdf_writes_each_field_it_maps(tmp_path: Path) -> None:
    """It said "Wrote metadata" and wrote nothing: the branch never ran."""
    path = tmp_path / "plain.pdf"
    shutil.copy(PDF_SOURCE_PATH, path)

    result = write_metadata(path, _PATCH, formats=["PDF"])

    assert result.written, result.error
    with pymupdf.open(path) as doc:
        info = doc.metadata or {}
    assert info["title"] == "New Title"
    assert "Jane Writer" in info["author"].split(",")
    assert "Horror" in info["subject"].split(",")
    assert "t1" in info["keywords"].split(",")
    assert info["creator"] == "Scanner X"
    assert info["producer"] == "Tagger Y"
    assert info["modDate"].startswith("D:20260102030405")
    # What the PDF had and the patch did not touch is kept.
    assert info["creationDate"].startswith("D:19700101")


def _with_notes_first(tmp_path: Path) -> Path:
    """Copy the ComicInfo PDF, with another attachment stored before ComicInfo."""
    path = tmp_path / "cix.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    with pymupdf.open(path) as doc:
        cix = doc.embfile_get(_CIX)
        doc.embfile_del(0)
        doc.embfile_add("notes.txt", _NOTES)
        doc.embfile_add(_CIX, cix)
        doc.saveIncr()
    return path


def _read_title(path: Path) -> str:
    with Comicbox(path) as box:
        return box.to_dict()["comicbox"]["title"]


def test_w_pdf_leaves_pages_and_other_attachments_as_they_were(
    tmp_path: Path,
) -> None:
    path = _with_notes_first(tmp_path)
    with pymupdf.open(path) as doc:
        pages = _pages(doc)

    result = write_metadata(path, {"title": "New Title"}, formats=["PDF"])

    assert result.written, result.error
    with pymupdf.open(path) as doc:
        assert (doc.metadata or {})["title"] == "New Title"
        assert _pages(doc) == pages
        assert doc.embfile_names() == ["notes.txt"]
        assert doc.embfile_get("notes.txt") == _NOTES


@pytest.mark.parametrize(
    ("formats", "has_cix"),
    [(["PDF"], False), (["PDF", "COMIC_INFO"], True), (["PDF", "keep"], True)],
    ids=["pdf", "pdf+cix", "pdf+keep"],
)
def test_what_w_pdf_writes_is_what_reads_back(
    tmp_path: Path, formats: list[str], has_cix: bool
) -> None:
    """
    -w pdf left the embedded ComicInfo, whose old title won the next read (B13b).

    Without keep, -w removes the tag files of formats not named, as in a zip.
    """
    path = _with_notes_first(tmp_path)

    result = write_metadata(path, {"title": "Second Title"}, formats=formats)

    assert result.written, result.error
    assert _read_title(path) == "Second Title"
    with pymupdf.open(path) as doc:
        names = doc.embfile_names()
        assert doc.embfile_get("notes.txt") == _NOTES
        assert (_CIX in names) is has_cix
        if has_cix:
            assert b"Second Title" in doc.embfile_get(_CIX)
