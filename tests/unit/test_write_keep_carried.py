"""
``-w keep``: where a comic carries its tags, and what keep may replace.

The default ComicInfo, formats carried twice, a PDF's embedded files, and
the tag sources that yield nothing or do not parse. Through the real write
path, on generated archives or copies of tests/files.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import zipfile
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.write import write_metadata
from tests.const import CIX_CBI_CBR_SOURCE_PATH, CIX_PDF_SOURCE_PATH, PDF_SOURCE_PATH
from tests.util.comics import JSON, make_comic

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"
_PATCH = {"summary": "Kept"}
_TAGS: dict[str, Any] = {"series": "Crimson Tide", "number": "1", "volume": 2006}


def _config(**dests: Any) -> Any:
    return get_config(Namespace(comicbox=Namespace(**dests)))


def _tag_files(path: Path) -> tuple[list[str], bytes]:
    """List a CBZ's tag files, by lower-case name, and its comment."""
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name.lower()
            for name in archive.namelist()
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        )
        return names, archive.comment


def _member(names: Iterable[str], filename: str) -> str:
    """Find the one archive member, at any depth, with this file name."""
    (name,) = (name for name in names if name.lower().endswith(filename.lower()))
    return name


def _tags(path: Path, config: Any = None) -> dict[str, Any]:
    with Comicbox(path, config=config) as box:
        return dict(box.to_dict()["comicbox"])


@pytest.mark.parametrize("source", ["cbr", "pdf"])
def test_keep_never_replaces_an_unread_comicinfo_with_the_default(
    tmp_path: Path, source: str
) -> None:
    """G1: the PDF-to-CBZ default fired for a CBR and replaced its ComicInfo."""
    path = tmp_path / f"comic.{source}"
    shutil.copy(
        CIX_CBI_CBR_SOURCE_PATH if source == "cbr" else CIX_PDF_SOURCE_PATH, path
    )
    with Comicbox(path) as box:
        name = _member(box.namelist(), "ComicInfo.xml")
        comic_info = box.get_page_by_filename(name)
    config = _config(
        **{
            "convert.cbz": True,
            "read.formats": ["mi", "fn"],
            "write.formats": ["keep"],
        }
    )

    with Comicbox(path, config=config) as box:
        box.dump()

    with zipfile.ZipFile(path.with_suffix(".cbz")) as archive:
        assert archive.read(name) == comic_info


def test_cbz_with_keep_adds_no_tag_file_to_an_untagged_comic(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "bare.cbz", formats=(), **_TAGS)
    config = _config(**{"convert.cbz": True, "write.formats": ["keep"]})

    with Comicbox(path, config=config) as box:
        box.dump()

    assert _tag_files(path) == ([], b"")


def test_cbz_with_keep_still_gives_a_pdf_its_default_comicinfo(tmp_path: Path) -> None:
    path = tmp_path / "plain.pdf"
    shutil.copy(PDF_SOURCE_PATH, path)
    config = _config(**{"convert.cbz": True, "write.formats": ["keep"]})

    with Comicbox(path, config=config) as box:
        box.dump()

    assert _tag_files(path.with_suffix(".cbz"))[0] == ["comicinfo.xml"]


def _cbi_text(**tags: Any) -> str:
    from comicbox.formats import MetadataFormats

    comic = {"series": {"name": tags["series"]}, "issue": {"name": tags["number"]}}
    return Comicbox(metadata={"comicbox": comic}).to_string(
        MetadataFormats.COMIC_BOOK_INFO
    )


def test_keep_rewrites_a_format_carried_twice_in_both_places(tmp_path: Path) -> None:
    """G2: only the comment was rewritten, and the stale file won the next read."""
    path = make_comic(
        tmp_path / "cw1.cbz",
        formats=(JSON, "COMIC_BOOK_INFO"),
        files={"comic-book-info.json": _cbi_text(**_TAGS)},
        **_TAGS,
    )

    write_metadata(path, {"series": {"name": "Kept Series"}}, formats=["keep"])

    with zipfile.ZipFile(path) as archive:
        as_file = json.loads(archive.read("comic-book-info.json"))
        as_comment = json.loads(archive.comment)
    assert as_file["ComicBookInfo/1.0"]["series"] == "Kept Series"
    assert as_comment["ComicBookInfo/1.0"]["series"] == "Kept Series"
    assert _tags(path)["series"]["name"] == "Kept Series"


def test_keep_rewrites_comicinfo_at_each_path_it_is_carried(tmp_path: Path) -> None:
    from comicbox.formats import MetadataFormats

    comic = {"series": {"name": "Crimson Tide"}, "issue": {"name": "1"}}
    cix = Comicbox(metadata={"comicbox": comic}).to_string(MetadataFormats.COMIC_INFO)
    path = make_comic(
        tmp_path / "cw1.cbz",
        formats=(_CIX,),
        files={"issue/ComicInfo.xml": cix},
        **_TAGS,
    )

    write_metadata(path, _PATCH, formats=["keep"])

    with zipfile.ZipFile(path) as archive:
        for name in ("ComicInfo.xml", "issue/ComicInfo.xml"):
            assert "Kept" in archive.read(name).decode()


def test_keep_rewrites_a_pdfs_own_metadata(tmp_path: Path) -> None:
    """B13: like any kept format, where G3 said there was nothing to keep."""
    import pymupdf

    path = tmp_path / "plain.pdf"
    shutil.copy(PDF_SOURCE_PATH, path)

    result = write_metadata(path, {"title": "Kept title"}, formats=["keep"])

    assert result.written, result.error
    with pymupdf.open(path) as doc:
        assert (doc.metadata or {})["title"] == "Kept title"
        assert doc.embfile_names() == []


def test_delete_all_tags_in_a_base_config_wins_over_keep(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_CIX, _MI), **_TAGS)
    base = _config(**{"write.delete_all_tags": True})

    write_metadata(path, _PATCH, formats=["keep"], base_config=base)

    assert _tag_files(path) == ([], b"")


def test_keep_refuses_an_unparseable_comic_in_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loguru import logger

    # The runner replaces every sink with its own; keep this test's.
    monkeypatch.setattr("comicbox.run.init_logging", lambda *_: None)

    path = make_comic(
        tmp_path / "broken.cbz",
        files={"ComicInfo.xml": "<ComicInfo><Series>A & B</Series></ComicInfo>"},
        **_TAGS,
    )
    untouched = path.read_bytes()
    messages: list[str] = []
    handler = logger.add(
        messages.append, level="ERROR", format="{message}\n{exception}"
    )
    try:
        with contextlib.suppress(SystemExit):
            cli.main(("comicbox", "-w", "keep", str(path)))
    finally:
        logger.remove(handler)

    assert len(messages) == 1
    assert "ComicInfo.xml could not be parsed, so keep cannot keep it" in messages[0]
    assert "Traceback" not in messages[0]
    assert path.read_bytes() == untouched


@pytest.mark.parametrize(
    ("extra", "files"),
    [
        # A well-formed ComicInfo that holds nothing.
        (
            {"files": {"ComicInfo.xml": "<ComicInfo></ComicInfo>"}},
            ["comicbox.json", "comicinfo.xml"],
        ),
        # Free text that starts with a brace, and JSON that is not ComicBookInfo.
        ({"comment": "{DCP} scanned by somebody"}, ["comicbox.json"]),
        ({"comment": '{"note": "not cbi"}'}, ["comicbox.json"]),
    ],
    ids=["empty-comicinfo", "brace-comment", "json-comment"],
)
def test_a_tag_source_that_yields_nothing_is_not_unparseable(
    tmp_path: Path, extra: dict[str, Any], files: list[str]
) -> None:
    """G4: these could never be written with keep, nor tagged by write-arcs."""
    path = make_comic(tmp_path / "cw1.cbz", **extra, **_TAGS)
    comment = _tag_files(path)[1]

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert result.written, result.error
    assert _tag_files(path) == (files, comment)
    assert _tags(path)["summary"] == "Kept"


def test_a_pdf_with_no_info_values_is_not_unparseable(tmp_path: Path) -> None:
    import pymupdf

    path = tmp_path / "noinfo.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    with pymupdf.open(path) as doc:
        doc.set_metadata({})
        doc.saveIncr()

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert result.written, result.error
    assert _tags(path)["summary"] == "Kept"


def _embed_in_order(path: Path, names: Sequence[str]) -> dict[str, bytes]:
    """Re-embed a PDF's tag files in this order; return their bytes."""
    import pymupdf

    with pymupdf.open(path) as doc:
        data = {name: doc.embfile_get(name) for name in names}
        while doc.embfile_names():
            # Only the first embedded file is ever removed rightly.
            doc.embfile_del(0)
        for name in names:
            doc.embfile_add(name, data[name])
        doc.saveIncr()
    return data


@pytest.mark.parametrize(
    "order",
    [("ComicInfo.xml", "MetronInfo.xml"), ("MetronInfo.xml", "ComicInfo.xml")],
)
def test_keep_leaves_a_pdfs_unread_embedded_file_byte_for_byte(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    path = tmp_path / "cix.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    write_metadata(path, _PATCH, formats=[_CIX, _MI])
    metron = _embed_in_order(path, order)["MetronInfo.xml"]

    result = write_metadata(
        path,
        {"summary": "Again"},
        formats=["keep"],
        base_config=_config(**{"read.formats": ["cix"]}),
    )

    assert result.written, result.error
    import pymupdf

    with pymupdf.open(path) as doc:
        assert sorted(doc.embfile_names()) == sorted(order)
        assert doc.embfile_get("MetronInfo.xml") == metron
        comic_info = doc.embfile_get("ComicInfo.xml")
    assert b"<Summary>Again</Summary>" in comic_info


def test_keep_carries_an_unread_comment_into_a_converted_cbz(tmp_path: Path) -> None:
    path = tmp_path / "comic.cbr"
    shutil.copy(CIX_CBI_CBR_SOURCE_PATH, path)
    with Comicbox(path) as box:
        comment = box._get_comment()

    result = write_metadata(
        path, _PATCH, formats=["keep"], base_config=_config(**{"read.formats": ["cix"]})
    )

    assert result.written, result.error
    assert comment
    with zipfile.ZipFile(path.with_suffix(".cbz")) as archive:
        assert archive.comment == comment
