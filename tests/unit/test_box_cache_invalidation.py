"""Regression tests for box cache invalidation and shared-schema state."""

from __future__ import annotations

import shutil
import threading
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_cbz(tmp_path: Path) -> Path:
    """Fresh copy of the test CBZ for each test."""
    target = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, target)
    return target


def test_add_metadata_after_normalization_is_not_ignored(tmp_cbz: Path) -> None:
    """
    Metadata added after a source has been normalized must reach the merge.

    add_source used to pop only _loaded; the normalize getter skips
    re-normalization whenever the source key exists, so the stale
    _normalized entry silently swallowed anything added later.
    """
    with Comicbox(tmp_cbz) as cb:
        before = cb.to_dict()  # triggers load + normalize + merge
        assert before["comicbox"].get("publisher", {}).get("name") != "AddedPub"
        cb.add_metadata(
            {"comicbox": {"publisher": {"name": "AddedPub"}}},
            MetadataFormats.COMICBOX_JSON,
        )
        after = cb.to_dict()
    assert after["comicbox"]["publisher"]["name"] == "AddedPub"


def test_to_dict_page_count_consistent_after_pageless_format(tmp_cbz: Path) -> None:
    """
    Each to_dict() computes pages under its own format context.

    Pages computation consults _dict_formats (only ComicInfo's schema has
    HAS_PAGES); the computed/merged caches used to memoize the first
    call's result, so a pages-less first format starved every later
    format of computed page data. A dump after another format must match
    a fresh instance's dump exactly.
    """
    with Comicbox(tmp_cbz) as cb:
        fresh = cb.to_dict(MetadataFormats.COMIC_INFO)
    with Comicbox(tmp_cbz) as cb:
        cb.to_dict(MetadataFormats.FILENAME)
        after_other_format = cb.to_dict(MetadataFormats.COMIC_INFO)
    assert after_other_format == fresh


def test_schema_path_is_thread_local(tmp_path: Path) -> None:
    """
    get_schema's path is per-thread, not shared instance state.

    Schema instances are cached process-wide; the warning-prefix path
    used to be an instance attribute, so -j N workers relabeled each
    other's in-flight warnings.
    """
    barrier = threading.Barrier(2)
    seen: dict[str, str | None] = {}

    def worker(name: str) -> None:
        schema = get_schema(ComicboxYamlSchema, path=tmp_path / f"{name}.cbz")
        barrier.wait()  # both threads have called set_path before reading
        seen[name] = schema._path

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen["a"] == str(tmp_path / "a.cbz")
    assert seen["b"] == str(tmp_path / "b.cbz")


def test_mupdf_config_key_present() -> None:
    """The natural spelling."""
    keys = MetadataFormats.PDF.value.config_keys
    assert "mupdf" in keys
