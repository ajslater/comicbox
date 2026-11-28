"""Regression tests for box cache invalidation and shared-schema state."""

from __future__ import annotations

import shutil
import threading
from argparse import Namespace
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.formats.sources import MetadataSources
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

    from comicbox.config.settings import ComicboxSettings


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


def _cix_write_config() -> ComicboxSettings:
    return get_config({"comicbox": {"write": {"formats": ["cix"]}}})


def test_online_sources_survive_a_write(tmp_cbz: Path) -> None:
    """
    A write must not discard what the online lookup fetched.

    The post-write reset kept only the API source, but the lookup is
    once-per-box (`_online_lookup_done_flag` outlives the reset), so the
    online sources were gone for good — leaving the post-write rename,
    and every later read, on pre-online metadata minus whatever the
    written formats happened to carry back. `sort_name` is Metron-only,
    so re-reading the ComicInfo.xml this write produced can't recover it.
    """
    payload = {
        "metron_api": {
            "id": 99,
            "series": {"name": "Online Series", "sort_name": "Online Series, The"},
        }
    }
    with Comicbox(tmp_cbz, config=_cix_write_config()) as cb:
        cb.add_source(
            MetadataSources.METRON_API, payload, fmt=MetadataFormats.METRON_API
        )
        before = cb.to_dict()["comicbox"]["series"]
        cb.dump()
        after = cb.to_dict()["comicbox"]["series"]
    assert before["sort_name"] == "Online Series, The"
    assert after == before


def test_every_added_api_metadata_survives_a_write(tmp_cbz: Path) -> None:
    """
    All added API metadata is carried across the write, not just the first.

    The reset re-seeded the API source from `_sources[API][0]`, so a
    second add_metadata() was dropped on the floor by any write.
    """
    with Comicbox(tmp_cbz, config=_cix_write_config()) as cb:
        cb.add_metadata({"comicbox": {"publisher": {"name": "AddedPub"}}})
        cb.add_metadata({"comicbox": {"series": {"sort_name": "Zed, The"}}})
        cb.dump()
        after = cb.to_dict()["comicbox"]
    assert after["publisher"]["name"] == "AddedPub"
    assert after["series"]["sort_name"] == "Zed, The"


def test_cover_paths_follow_added_metadata(tmp_cbz: Path) -> None:
    """
    Covers come from the metadata, so adding metadata finds them again.

    _cover_paths was reset only with the archive, not with the other
    metadata-derived caches, so get_cover_paths() kept the old answer.
    """
    added = {"comicbox": {"pages": {2: {"page_type": "FrontCover"}}}}
    with Comicbox(tmp_cbz) as cb:
        before = cb.get_cover_paths()
        cb.add_metadata(added, MetadataFormats.COMICBOX_JSON)
        after = cb.get_cover_paths()
    with Comicbox(tmp_cbz, metadata=added, fmt=MetadataFormats.COMICBOX_JSON) as cb:
        fresh = cb.get_cover_paths()
    assert len(before) == 1
    assert len(fresh) == 2
    assert after == fresh


class _TickingClock(datetime):
    """A datetime whose now() is a second later on every call."""

    calls = 0

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _TickingClock:  # pyright: ignore[reportIncompatibleMethodOverride]
        cls.calls += 1
        return cls(2026, 1, 1, 0, 0, cls.calls, tzinfo=tz)


def test_one_instance_stamps_every_format_alike(
    tmp_cbz: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Every format one Comicbox renders carries the same updated_at.

    Each format switch reruns the computed pass, and the stamp took a fresh
    clock reading every time, so tag files written together disagreed
    whenever their writes straddled a second.
    """
    monkeypatch.setattr(_TickingClock, "calls", 0)
    monkeypatch.setattr("comicbox.box.computed.stamp.datetime", _TickingClock)
    config = get_config(Namespace(comicbox=Namespace(write=Namespace(stamp=True))))
    stamps = []
    with Comicbox(tmp_cbz, config=config) as cb:
        for fmt in (
            MetadataFormats.COMIC_INFO,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_BOOK_INFO,
        ):
            cb.to_dict(fmt)
            stamps.append(cb._metadata["comicbox"]["updated_at"])
        cb.add_metadata({"comicbox": {"title": "Restamped"}})
        cb.to_dict(MetadataFormats.COMIC_INFO)
        restamped = cb._metadata["comicbox"]["updated_at"]
    assert len(set(stamps)) == 1
    # New metadata is a new stamp.
    assert restamped > stamps[0]
