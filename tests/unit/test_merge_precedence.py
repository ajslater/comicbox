"""
End-to-end merge precedence: which source wins, and which format inside it.

`read.merge_order` had tests at the config-parsing layer only — nothing
asserted which metadata actually came out the other end. These pin the
two orderings the merge is built on: `MetadataSources` order (overridable
by `read.merge_order`) across sources, and `reversed(source.formats)`
within one source.

The fixture carries the same field in three places at three precedence
levels: `ComicInfo.xml` (series A) and `comicbox.json` (series B) are both
the ARCHIVE_FILE source, and the archive comment (series C) is
ARCHIVE_COMMENT.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.box.init import LoadedMetadata
from comicbox.box.merge import ComicboxMerge
from comicbox.config import get_config
from comicbox.config.settings import ComicboxSettings, WriteMode
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from pathlib import Path

_COMIC_INFO = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
  <Series>A</Series>
  <Writer>Joe</Writer>
</ComicInfo>
"""
_COMICBOX_JSON = json.dumps(
    {
        "comicbox": {
            "series": {"name": "B"},
            "credits": {"Wally": {"roles": {"Inker": {}}}},
        }
    }
)
_COMIC_BOOK_INFO = json.dumps(
    {"appID": "test", "ComicBookInfo/1.0": {"series": "C", "numberOfVolumes": 4}}
).encode()

# The filename parses to series "Merge Precedence"; ARCHIVE_FILENAME sits
# below both metadata sources by default, so it only shows up when an
# explicit merge_order promotes it.
_STEM = "Merge Precedence #001 (2001)"


@pytest.fixture
def cbz(tmp_path: Path) -> Path:
    """Build a CBZ carrying series A, B and C in three different places."""
    path = tmp_path / f"{_STEM}.cbz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("page-0.jpg", b"not-a-real-jpeg")
        zf.writestr("ComicInfo.xml", _COMIC_INFO)
        zf.writestr("comicbox.json", _COMICBOX_JSON)
        zf.comment = _COMIC_BOOK_INFO
    return path


def _read(path: Path, config: ComicboxSettings | None = None) -> dict:
    with Comicbox(path, config=config) as cb:
        return dict(cb.to_dict()["comicbox"])


def _merge_order(*names: str) -> ComicboxSettings:
    return get_config({"comicbox": {"read": {"merge_order": list(names)}}})


def _write_mode(mode: WriteMode) -> ComicboxSettings:
    """Set write.mode the way the public write API does."""
    config = get_config()
    return replace(config, write=replace(config.write, mode=mode))


###########################
# Source & format ordering #
###########################


def test_default_order_prefers_comicbox_json_over_comic_info(cbz: Path) -> None:
    """Within ARCHIVE_FILE, the earlier-declared format wins: B over A."""
    assert _read(cbz)["series"]["name"] == "B"


def test_default_order_prefers_archive_files_over_the_comment(cbz: Path) -> None:
    """ARCHIVE_FILE outranks ARCHIVE_COMMENT, so C never surfaces as the name."""
    series = _read(cbz)["series"]
    assert series["name"] == "B"
    # The comment still contributes what nothing above it set.
    assert series["volume_count"] == 4


def test_explicit_merge_order_matching_the_default_changes_nothing(
    cbz: Path,
) -> None:
    """Spelling out the default relative order yields the default winner."""
    config = _merge_order("ARCHIVE_FILENAME", "ARCHIVE_COMMENT", "ARCHIVE_FILE")
    assert _read(cbz, config)["series"]["name"] == "B"


def test_reversed_merge_order_lets_the_comment_win(cbz: Path) -> None:
    """Promoting ARCHIVE_COMMENT past ARCHIVE_FILE makes C the winner."""
    config = _merge_order("ARCHIVE_FILENAME", "ARCHIVE_FILE", "ARCHIVE_COMMENT")
    assert _read(cbz, config)["series"]["name"] == "C"


def test_unlisted_sources_are_appended_below_the_listed_ones(cbz: Path) -> None:
    """
    merge_order lists a prefix; the rest keep enum order *after* it.

    Naming only the two metadata sources leaves ARCHIVE_FILENAME in the
    appended remainder — above both — so the filename parse wins.
    """
    config = _merge_order("ARCHIVE_FILE", "ARCHIVE_COMMENT")
    assert _read(cbz, config)["series"]["name"] == "Merge Precedence"


def _loaded(fmt: MetadataFormats | None, name: str) -> LoadedMetadata:
    return LoadedMetadata({"comicbox": {"series": {"name": name}}}, None, fmt)


def test_formats_outside_the_source_sort_last_instead_of_raising() -> None:
    """
    A format the source doesn't declare gets its own bucket, at the end.

    `add_metadata(md, fmt=...)` accepts any format, including the online
    ones no source's tuple lists, and the fixed-key bucket lookup raised
    KeyError on every one of them. `fmt=None` was dropped outright.
    Undeclared formats merge last, so an explicitly-passed format outranks
    the source's own.
    """
    order = ComicboxMerge._order_normalized_md_by_format(
        MetadataSources.API,
        (
            _loaded(MetadataFormats.METRON_API, "online"),
            _loaded(MetadataFormats.COMIC_INFO, "declared"),
            _loaded(None, "unknown"),
        ),
    )
    names = [md["comicbox"]["series"]["name"] for md in order]
    assert names == ["declared", "online", "unknown"]


def test_add_metadata_with_an_online_format_merges(cbz: Path) -> None:
    """The public API path that used to raise KeyError now wins the merge."""
    payload = {"metron_api": {"id": 7, "series": {"name": "Online"}}}
    with Comicbox(cbz) as cb:
        cb.add_metadata(payload, fmt=MetadataFormats.METRON_API)
        assert cb.to_dict()["comicbox"]["series"]["name"] == "Online"


#################################
# Read merge vs. write settings #
#################################


@pytest.mark.parametrize("mode", list(WriteMode))
def test_reads_are_identical_under_every_write_mode(cbz: Path, mode: WriteMode) -> None:
    """
    `to_dict()` must not depend on how a hypothetical write would merge.

    Under `update` the cross-source merge was `dict.update` at the root,
    so comicbox.json's `credits` replaced ComicInfo's wholesale and Joe
    vanished from a plain read.
    """
    md = _read(cbz, _write_mode(mode))
    assert md == _read(cbz)
    assert set(md["credits"]) == {"Joe", "Wally"}


def test_legacy_replace_bool_does_not_change_a_read(cbz: Path) -> None:
    """The deprecated `write.replace` alias is a write knob too."""
    config = get_config({"comicbox": {"write": {"replace": True}}})
    assert _read(cbz, config) == _read(cbz)


@pytest.mark.parametrize(
    ("mode", "expect_sibling"),
    [
        (WriteMode.ADDITIVE, True),
        (WriteMode.REPLACE, True),
        (WriteMode.UPDATE, False),
    ],
)
def test_write_mode_still_governs_the_supplied_patch(
    cbz: Path, mode: WriteMode, *, expect_sibling: bool
) -> None:
    """
    The patch keeps its documented per-mode semantics against the archive.

    `update` replaces `series` wholesale — dropping the `volume_count`
    the archive comment supplied — while the deep modes keep it.
    """
    patch = {"comicbox": {"series": {"name": "D"}}}
    with Comicbox(cbz, config=_write_mode(mode), metadata=patch) as cb:
        series = cb.to_dict()["comicbox"]["series"]
    assert series["name"] == "D"
    assert ("volume_count" in series) is expect_sibling
