"""
-w naming nothing this archive can hold is refused (D9, section 10).

-w removes the tag formats it does not name, and a PDF's own metadata cannot
go into a zip, so -w pdf on a CBZ removed every tag file and wrote none; -w fn
and -w pdfxml did the same on any archive. AJ: "Yes, refuse it".
"""

from __future__ import annotations

import shutil
import zipfile
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox import cli
from comicbox.config import get_config
from comicbox.exceptions import UnwritableFormatError
from comicbox.write import BulkWriteItem, bulk_write, write_metadata
from tests.const import (
    CIX_CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    CIX_PDF_SOURCE_PATH,
)

if TYPE_CHECKING:
    from pathlib import Path

_CBZ = CIX_CBZ_SOURCE_PATH
_SOURCES = {"cbz": _CBZ, "cbr": CIX_CBI_CBR_SOURCE_PATH, "cbt": CIX_CBT_SOURCE_PATH}


def _config(**dests: Any) -> Any:
    return get_config(Namespace(comicbox=Namespace(**dests)))


def _copy(tmp_path: Path, source: Path, name: str | None = None) -> Path:
    path = tmp_path / (name or f"comic{source.suffix}")
    shutil.copy(source, path)
    return path


def _tag_files(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return [name for name in archive.namelist() if name.lower().endswith(".xml")]


def _warnings(run: Any) -> tuple[Any, list[str]]:
    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        return run(), messages
    finally:
        logger.remove(handler)


@pytest.mark.parametrize("convert", [False, True], ids=["in place", "--cbz"])
@pytest.mark.parametrize("kind", list(_SOURCES))
def test_w_pdf_on_a_comic_that_is_not_a_pdf_is_refused(
    tmp_path: Path, kind: str, convert: bool
) -> None:
    path = _copy(tmp_path, _SOURCES[kind])
    before = path.read_bytes()

    result = write_metadata(
        path,
        {"summary": "New"},
        formats=["PDF"],
        base_config=_config(**{"convert.cbz": convert}),
    )

    assert not result.written
    assert isinstance(result.error, UnwritableFormatError)
    assert "MuPDF" in str(result.error)
    assert path.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {path.name}


@pytest.mark.parametrize("name", ["FILENAME", "PDF_XML"])
def test_a_format_no_archive_can_hold_is_refused_too(tmp_path: Path, name: str) -> None:
    path = _copy(tmp_path, _CBZ)
    before = path.read_bytes()

    result = write_metadata(path, {"summary": "New"}, formats=[name])

    assert isinstance(result.error, UnwritableFormatError)
    assert path.read_bytes() == before


def test_the_cli_refuses_in_one_line_and_exits_1(tmp_path: Path) -> None:
    path = _copy(tmp_path, _CBZ)
    before = path.read_bytes()

    with pytest.raises(SystemExit) as exited:
        cli.main(("comicbox", "-w", "pdf", str(path)))

    assert exited.value.code == 1
    assert path.read_bytes() == before


def test_bulk_write_returns_the_refusal(tmp_path: Path) -> None:
    path = _copy(tmp_path, _CBZ)

    (result,) = bulk_write(
        [BulkWriteItem(path, {"summary": "New"}, formats=frozenset({"PDF"}))]
    )

    assert isinstance(result.error, UnwritableFormatError)


def test_a_format_it_can_hold_beside_one_it_cannot_is_written(tmp_path: Path) -> None:
    path = _copy(tmp_path, _CBZ)

    result, warnings = _warnings(
        lambda: write_metadata(path, {"summary": "New"}, formats=["PDF", "COMIC_INFO"])
    )

    assert result.written, result.error
    assert _tag_files(path) == ["ComicInfo.xml"]
    assert any("cannot hold MuPDF" in message for message in warnings)


def test_keep_beside_one_it_cannot_hold_writes_the_carried_formats(
    tmp_path: Path,
) -> None:
    path = _copy(tmp_path, _CBZ)
    carried = _tag_files(path)

    result, warnings = _warnings(
        lambda: write_metadata(path, {"summary": "Kept"}, formats=["PDF", "keep"])
    )

    assert result.written, result.error
    assert _tag_files(path) == carried
    assert any("cannot hold MuPDF" in message for message in warnings)


def test_a_pdf_converted_to_a_cbz_keeps_its_comicinfo_default(tmp_path: Path) -> None:
    path = _copy(tmp_path, CIX_PDF_SOURCE_PATH)

    result = write_metadata(
        path,
        {"summary": "New"},
        formats=["PDF"],
        base_config=_config(**{"convert.cbz": True}),
    )

    assert result.written, result.error
    assert _tag_files(path.with_suffix(".cbz")) == ["ComicInfo.xml"]


def test_delete_all_tags_names_no_format_and_is_unaffected(tmp_path: Path) -> None:
    path = _copy(tmp_path, _CBZ)

    result = write_metadata(
        path,
        {"summary": "Ignored"},
        formats=["COMIC_INFO"],
        base_config=_config(**{"write.delete_all_tags": True}),
    )

    assert result.written, result.error
    assert _tag_files(path) == []
