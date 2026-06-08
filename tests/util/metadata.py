"""Metadata read/compare helpers and write-metadata factories."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any

from glom import Assign, Delete, glom

from comicbox.box import Comicbox
from comicbox.box.pages.covers import PAGES_KEYPATH
from comicbox.formats.comic_book_info.transform import UPDATED_AT_KEYPATH
from comicbox.formats.comicbox.schema import (
    NOTES_KEY,
    PAGE_COUNT_KEY,
    ComicboxSchemaMixin,
)
from tests.const import TEST_WRITE_NOTES

from .diff import assert_diff

PAGE_COUNT_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{PAGE_COUNT_KEY}"
NOTES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{NOTES_KEY}"


def read_metadata(
    archive_path: Path,
    metadata: Mapping[str, Any],
    read_config: Any,
    *,
    ignore_updated_at: bool,
    ignore_notes: bool,
    page_count: int | None = None,
    ignore_page_count: bool = False,
    ignore_pages: bool = False,
) -> None:
    """Read metadata and compare to dict fixture."""
    with Comicbox(archive_path, config=read_config) as car:
        disk_md = dict(car.get_internal_metadata())

    md: dict[str, Any] = dict(metadata)
    if ignore_page_count:
        glom(md, Delete(PAGE_COUNT_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(PAGE_COUNT_KEYPATH, ignore_missing=True))
    elif page_count is not None:
        glom(md, Assign(PAGE_COUNT_KEYPATH, page_count, missing=dict))
    if ignore_updated_at:
        glom(md, Delete(UPDATED_AT_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(UPDATED_AT_KEYPATH, ignore_missing=True))
    if ignore_notes:
        glom(md, Delete(NOTES_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(NOTES_KEYPATH, ignore_missing=True))
    if ignore_pages:
        glom(md, Delete(PAGES_KEYPATH, ignore_missing=True))
        glom(disk_md, Delete(PAGES_KEYPATH, ignore_missing=True))
    frozen_md = MappingProxyType(md)
    frozen_disk_md = MappingProxyType(disk_md)
    assert_diff(frozen_md, frozen_disk_md)


def create_write_metadata(
    read_metadata: MappingProxyType[str, Any], notes: str = TEST_WRITE_NOTES
) -> MappingProxyType[str, Any]:
    """Create a write metadata from read metadata."""
    result = deepcopy(dict(read_metadata))
    result[ComicboxSchemaMixin.ROOT_TAG]["notes"] = notes
    return MappingProxyType(result)


def create_write_dict(
    read_dict: MappingProxyType[str, Any],
    schema_class: Any,
    notes_tag: str,
    notes: str = TEST_WRITE_NOTES,
) -> MappingProxyType[str, Any]:
    """Create a write dict from read dict."""
    write_dict = deepcopy(dict(read_dict))
    write_dict[schema_class.ROOT_TAG][notes_tag] = notes
    return MappingProxyType(write_dict)
