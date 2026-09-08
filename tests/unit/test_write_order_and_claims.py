"""
Where metadata sits in a CBZ, and who is allowed to write it.

An in-place re-tag removes the archive's metadata members and repacks.
``repack()`` only shifts entries that follow a removed one, so metadata
written at the front makes every later write slide the whole archive
down over its own pages — the pages are then in the write path, and an
interrupted or concurrent write lands on them.
"""

from __future__ import annotations

import shutil
import zipfile
from typing import TYPE_CHECKING

from comicbox.box.archive.write import _claim_destination, _release_destination
from comicbox.exceptions import ArchiveWriteError
from comicbox.write import BulkWriteItem, bulk_write, write_metadata
from tests.const import CIX_CBT_SOURCE_PATH, CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_CIX = ["COMIC_INFO"]
_CIX_SET = frozenset({"COMIC_INFO"})
_PAGE_SUFFIX = ".jpg"


def _page_offsets(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as zf:
        return {
            info.filename: info.header_offset
            for info in zf.infolist()
            if info.filename.endswith(_PAGE_SUFFIX)
        }


def _last_page_offset(path: Path) -> int:
    return max(_page_offsets(path).values())


def _metadata_offsets(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as zf:
        return {
            info.filename: info.header_offset
            for info in zf.infolist()
            if not info.filename.endswith(_PAGE_SUFFIX)
        }


def _convert(tmp_path: Path, name: str) -> Path:
    """Convert the test CBT so the archive under test is one comicbox wrote."""
    cbt = tmp_path / f"{name}.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)
    result = next(
        iter(
            bulk_write(
                [BulkWriteItem(path=cbt, patch={"title": "a"}, formats=_CIX_SET)]
            )
        )
    )
    assert result.written
    assert result.final_path is not None
    return result.final_path


def test_a_converted_archive_puts_its_metadata_after_every_page(
    tmp_path: Path,
) -> None:
    """Metadata trails the pages, so a later repack has nothing to shift."""
    cbz = _convert(tmp_path, "Order v1 #001 (2001)")

    metadata = _metadata_offsets(cbz)
    assert metadata
    assert min(metadata.values()) > _last_page_offset(cbz)


def test_an_in_place_rewrite_never_moves_page_data(tmp_path: Path) -> None:
    """
    Re-tagging leaves every page at the byte offset it already occupied.

    With metadata at the front this failed: removing it made repack slide
    all five pages down, rewriting the whole archive over itself. Any
    interruption then landed on page bytes rather than on the metadata.
    """
    cbz = _convert(tmp_path, "Stable v1 #001 (2001)")
    before = _page_offsets(cbz)
    with zipfile.ZipFile(cbz) as zf:
        page_bytes = {name: zf.read(name) for name in before}

    for run in range(2):
        assert write_metadata(cbz, patch={"title": f"run{run}"}, formats=_CIX).written
        assert _page_offsets(cbz) == before

    with zipfile.ZipFile(cbz) as zf:
        assert {name: zf.read(name) for name in before} == page_bytes


def test_metadata_stays_last_across_repeated_writes(tmp_path: Path) -> None:
    """The layout maintains itself: new metadata is appended, not prepended."""
    cbz = _convert(tmp_path, "Repeat v1 #001 (2001)")

    for run in range(2):
        assert write_metadata(
            cbz, patch={"title": f"run{run}"}, formats=["COMIC_INFO", "COMICBOX_YAML"]
        ).written
        metadata = _metadata_offsets(cbz)
        assert metadata
        assert min(metadata.values()) > _last_page_offset(cbz)


def test_an_in_place_write_respects_a_held_destination(tmp_path: Path) -> None:
    """
    An in-place write claims its archive, as a conversion claims its output.

    Only conversions used to claim, so two writers on one CBZ repacked it
    at once and destroyed it. Holding the path stands in for the other
    writer, which leaves nothing on disk for any file check to see.
    """
    cbz = tmp_path / "Held v1 #001 (2001).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    before = cbz.read_bytes()

    _claim_destination(cbz)
    try:
        result = write_metadata(cbz, patch={"title": "z"}, formats=_CIX)
    finally:
        _release_destination(cbz)

    assert not result.written
    assert isinstance(result.error, ArchiveWriteError)
    assert "already being written" in str(result.error)
    # Refused before touching anything.
    assert cbz.read_bytes() == before

    # And the claim is released, so the same write goes through afterwards.
    assert write_metadata(cbz, patch={"title": "z"}, formats=_CIX).written


def test_one_archive_named_twice_in_a_batch_survives(tmp_path: Path) -> None:
    """
    Two writers on one path: one wins, one is refused, the comic is intact.

    ``bulk_write`` does not deduplicate paths, so this ran two concurrent
    in-place repacks over the same bytes. It destroyed every page in
    roughly one run out of three.
    """
    cbz = tmp_path / "Twice v1 #001 (2001).cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, cbz)
    with zipfile.ZipFile(cbz) as zf:
        pages = {n: zf.read(n) for n in zf.namelist() if n.endswith(_PAGE_SUFFIX)}
    assert pages

    results = list(
        bulk_write(
            [
                BulkWriteItem(path=cbz, patch={"title": f"t{i}"}, formats=_CIX_SET)
                for i in range(2)
            ],
            workers=2,
        )
    )

    assert sum(r.written for r in results) == 1
    refused = next(r for r in results if not r.written)
    assert "already being written" in str(refused.error)

    with zipfile.ZipFile(cbz) as zf:
        assert {
            n: zf.read(n) for n in zf.namelist() if n.endswith(_PAGE_SUFFIX)
        } == pages
