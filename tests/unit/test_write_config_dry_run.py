"""
A config that sets `general.dry_run` writes nothing and says so.

`dump()` honours the config's dry run, but `_write_comic` reported every
call it made as written, so `write_metadata` and `bulk_write` claimed a
write, and for a CBT a conversion to CBZ, that never happened.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox.config import get_config
from comicbox.write import BulkWriteItem, bulk_write, write_metadata
from tests.const import CIX_CBT_SOURCE_PATH, CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_FORMATS = frozenset({"COMIC_INFO"})


def _dry_run_config():
    return get_config({"comicbox": {"general": {"dry_run": True}}})


@pytest.fixture(params=[CIX_CBZ_SOURCE_PATH, CIX_CBT_SOURCE_PATH], ids=["cbz", "cbt"])
def comic(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    path = tmp_path / f"comic{request.param.suffix}"
    shutil.copy(request.param, path)
    return path


def _assert_untouched(comic: Path, before: bytes) -> None:
    assert comic.read_bytes() == before
    assert sorted(p.name for p in comic.parent.iterdir()) == [comic.name]


def test_write_metadata_under_a_config_dry_run(comic: Path) -> None:
    before = comic.read_bytes()
    result = write_metadata(
        comic, {"title": "x"}, formats=_FORMATS, base_config=_dry_run_config()
    )
    assert result.error is None
    assert result.written is False
    assert result.final_path is None
    assert result.dry_run_payload is not None
    assert "COMIC_INFO" in result.dry_run_payload
    _assert_untouched(comic, before)


def test_bulk_write_under_a_config_dry_run(comic: Path) -> None:
    before = comic.read_bytes()
    item = BulkWriteItem(path=comic, patch={"title": "x"}, formats=_FORMATS)
    (result,) = bulk_write([item], base_config=_dry_run_config())
    assert result.error is None
    assert result.written is False
    _assert_untouched(comic, before)


def test_without_a_dry_run_it_still_writes(comic: Path) -> None:
    result = write_metadata(comic, {"title": "x"}, formats=_FORMATS)
    assert result.error is None
    assert result.written is True
    assert result.final_path is not None
    assert result.final_path.suffix == ".cbz"
