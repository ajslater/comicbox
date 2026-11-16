"""-w pdf writes a PDF's own metadata, and nothing else (B13)."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pymupdf

from comicbox.write import write_metadata
from tests.const import CIX_PDF_SOURCE_PATH, PDF_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

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


def test_w_pdf_leaves_pages_and_attachments_as_they_were(tmp_path: Path) -> None:
    path = tmp_path / "cix.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    with pymupdf.open(path) as doc:
        doc.embfile_add("notes.txt", b"the scanner's notes")
        doc.saveIncr()
    with pymupdf.open(path) as doc:
        pages = _pages(doc)
        attachments = {name: doc.embfile_get(name) for name in doc.embfile_names()}

    result = write_metadata(path, {"title": "New Title"}, formats=["PDF"])

    assert result.written, result.error
    with pymupdf.open(path) as doc:
        assert (doc.metadata or {})["title"] == "New Title"
        assert _pages(doc) == pages
        assert {
            name: doc.embfile_get(name) for name in doc.embfile_names()
        } == attachments
