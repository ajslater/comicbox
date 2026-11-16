"""
A write whose patch does not load writes nothing, and says so (D7, section 10).

``write_metadata`` returned ``written=True`` for a patch that failed to load
("Unable to load API"), having rewritten the comic from its own tags with none
of the patch applied. So did ``bulk_write``.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.exceptions import MetadataError
from comicbox.write import BulkWriteItem, bulk_write, write_metadata
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from pathlib import Path

_SOURCE = TEST_FILES_DIR / "Captain Science #001-cix.cbz"
_UNLOADABLE = [{"bogus": 1}, {"series": ["a", "list"]}, {"issue": 7}]


def _copy(tmp_path: Path) -> Path:
    path = tmp_path / "comic.cbz"
    shutil.copy(_SOURCE, path)
    return path


@pytest.mark.parametrize(
    "patch", _UNLOADABLE, ids=["unknown key", "list series", "int issue"]
)
def test_a_patch_that_does_not_load_writes_nothing(
    tmp_path: Path, patch: dict[str, Any]
) -> None:
    path = _copy(tmp_path)
    before = path.read_bytes()

    result = write_metadata(path, patch, formats=["COMIC_INFO"])

    assert not result.written
    assert isinstance(result.error, MetadataError)
    assert path.read_bytes() == before


def test_bulk_write_reports_a_patch_that_does_not_load(tmp_path: Path) -> None:
    path = _copy(tmp_path)
    before = path.read_bytes()

    (result,) = bulk_write(
        [BulkWriteItem(path, {"bogus": 1}, formats=frozenset({"COMIC_INFO"}))]
    )

    assert not result.written
    assert isinstance(result.error, MetadataError)
    assert path.read_bytes() == before


def test_a_patch_with_one_bad_value_still_writes_the_rest(tmp_path: Path) -> None:
    path = _copy(tmp_path)

    result = write_metadata(
        path, {"summary": "Applied", "series": ["a", "list"]}, formats=["COMIC_INFO"]
    )

    assert result.written, result.error
    with Comicbox(path) as box:
        assert box.to_dict()["comicbox"]["summary"] == "Applied"
