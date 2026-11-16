"""--cbz without -w writes back the formats the comic carried (B9)."""

from __future__ import annotations

import json
import shutil
import zipfile
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from tests.const import (
    CBI_CBR_SOURCE_PATH,
    CIX_CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
)
from tests.util.comics import make_comic

if TYPE_CHECKING:
    from pathlib import Path

_PAGES = (".jpg", ".jpeg", ".png", ".webp")


def _convert(path: Path, **dests: Any) -> tuple[list[str], bytes]:
    config = get_config(Namespace(comicbox=Namespace(**{"convert.cbz": True, **dests})))
    with Comicbox(path, config=config) as box:
        box.dump()
    with zipfile.ZipFile(path.with_suffix(".cbz")) as archive:
        names = [n for n in archive.namelist() if not n.lower().endswith(_PAGES)]
        return sorted(names), archive.comment


def test_a_comment_stays_a_comment_and_m_merges_into_it(tmp_path: Path) -> None:
    """It gave comicbox-cli.yaml, and the comment came back as a file."""
    path = tmp_path / "comic.cbr"
    shutil.copy(CBI_CBR_SOURCE_PATH, path)

    names, comment = _convert(path, **{"general.metadata_cli": ["{summary: given}"]})

    assert names == []
    assert json.loads(comment)["ComicBookInfo/1.0"]["comments"] == "given"


def test_a_tag_file_and_a_comment_each_come_back_as_they_were(tmp_path: Path) -> None:
    path = tmp_path / "comic.cbr"
    shutil.copy(CIX_CBI_CBR_SOURCE_PATH, path)

    names, comment = _convert(path)

    assert names == ["ComicInfo.xml"]
    assert "ComicBookInfo/1.0" in json.loads(comment)


def test_tag_files_are_written_as_before(tmp_path: Path) -> None:
    path = tmp_path / "comic.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, path)
    names, comment = _convert(path)
    assert names == ["ComicInfo.xml", "MetronInfo.xml"]
    assert comment == b""


def test_a_comic_that_carried_nothing_says_where_m_went(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "bare.cbz", formats=(), series="X", number="1")
    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        names, _ = _convert(path, **{"general.metadata_cli": ["{summary: given}"]})
    finally:
        logger.remove(handler)

    assert names == []
    assert any("carries no tag format" in message for message in messages)


@pytest.mark.parametrize("source", [CBI_CBR_SOURCE_PATH, CIX_CBI_CBR_SOURCE_PATH])
def test_named_formats_are_unchanged(tmp_path: Path, source: Path) -> None:
    path = tmp_path / "comic.cbr"
    shutil.copy(source, path)
    names, comment = _convert(path, **{"write.formats": ["cix"]})
    assert names == ["ComicInfo.xml"]
    assert comment == b""
