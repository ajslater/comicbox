"""Tests for the public write API: write_metadata + bulk_write."""

from __future__ import annotations

import shutil
import threading
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.events import BatchFinished, BatchStarted, Event, FileParsed
from comicbox.write import (
    BulkWriteItem,
    WriteValidationError,
    bulk_write,
    write_metadata,
)
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def tmp_cbz(tmp_path: Path) -> Path:
    """Fresh copy of the test CBZ for each test."""
    target = tmp_path / "test.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, target)
    return target


def _read_publisher(path: Path) -> dict:
    with Comicbox(path) as cb:
        return cb.get_internal_metadata().get("comicbox", {}).get("publisher") or {}


# --- single-file write ------------------------------------------------------


def test_write_metadata_replaces_scalar_preserving_siblings(tmp_cbz: Path) -> None:
    """Replace mode changes the name leaf, leaves nested siblings intact."""
    # Seed the comic with publisher.name + publisher.identifiers
    initial = {
        "publisher": {
            "name": "Original",
            "identifiers": {"metron": {"key": "42", "url": "https://x/42"}},
        }
    }
    write_metadata(tmp_cbz, patch=initial, mode="replace", formats=["comicbox_json"])

    # Patch only the name
    result = write_metadata(
        tmp_cbz,
        patch={"publisher": {"name": "Foo"}},
        mode="replace",
        formats=["comicbox_json"],
    )
    assert result.written is True
    assert result.error is None

    pub = _read_publisher(tmp_cbz)
    assert pub["name"] == "Foo"
    assert pub["identifiers"]["metron"]["key"] == "42"


def test_write_metadata_additive_recurses_into_publisher_dict(tmp_cbz: Path) -> None:
    """
    Additive mode recurses into dicts and only replaces leaves.

    AdditiveMerger and ReplaceMerger both replace scalars at conflicting
    paths (mergedeep ADDITIVE falls through to REPLACE for non-collection
    leaves). The distinction is list-typed fields: ADDITIVE concats,
    REPLACE overwrites. For dict-of-dict comicbox schema fields the two
    behave identically.
    """
    initial = {
        "publisher": {
            "name": "Original",
            "identifiers": {"metron": {"key": "42"}},
        }
    }
    write_metadata(tmp_cbz, patch=initial, mode="replace", formats=["comicbox_json"])
    write_metadata(
        tmp_cbz,
        patch={"publisher": {"name": "Foo"}},
        mode="additive",
        formats=["comicbox_json"],
    )
    pub = _read_publisher(tmp_cbz)
    # Scalar replaced at the leaf (ADDITIVE behavior matches REPLACE here).
    assert pub["name"] == "Foo"
    # Sibling key untouched — this is the dict-recursion contract that
    # distinguishes additive/replace from update.
    assert pub["identifiers"]["metron"]["key"] == "42"


def test_write_metadata_update_replaces_top_level_key(tmp_cbz: Path) -> None:
    """Update mode replaces the entire publisher value — siblings dropped."""
    write_metadata(
        tmp_cbz,
        patch={
            "publisher": {
                "name": "Original",
                "identifiers": {"metron": {"key": "42"}},
            }
        },
        mode="replace",
        formats=["comicbox_json"],
    )
    write_metadata(
        tmp_cbz,
        patch={"publisher": {"name": "Foo"}},
        mode="update",
        formats=["comicbox_json"],
    )
    pub = _read_publisher(tmp_cbz)
    assert pub.get("name") == "Foo"
    assert "identifiers" not in pub


def test_write_metadata_dry_run_returns_payload(tmp_cbz: Path) -> None:
    """dry_run=True returns the serialised would-be-written content."""
    result = write_metadata(
        tmp_cbz,
        patch={"publisher": {"name": "Foo"}},
        mode="replace",
        formats=["comic_info"],
        dry_run=True,
    )
    assert result.written is False
    assert result.dry_run_payload is not None
    assert "COMIC_INFO" in result.dry_run_payload
    assert "Foo" in result.dry_run_payload["COMIC_INFO"]
    # Archive must NOT have been touched.
    assert "Foo" not in _read_publisher(tmp_cbz).get("name", "")


def test_write_metadata_rejects_empty_patch(tmp_cbz: Path) -> None:
    with pytest.raises(WriteValidationError, match="non-empty"):
        write_metadata(tmp_cbz, patch={}, formats=["comic_info"])


def test_write_metadata_rejects_unknown_mode(tmp_cbz: Path) -> None:
    with pytest.raises(WriteValidationError, match="Unknown mode"):
        write_metadata(
            tmp_cbz,
            patch={"publisher": {"name": "x"}},
            mode="bogus",  # pyright: ignore[reportArgumentType]
            formats=["comic_info"],
        )


def test_write_metadata_rejects_missing_formats(tmp_cbz: Path) -> None:
    with pytest.raises(WriteValidationError, match="at least one format"):
        write_metadata(tmp_cbz, patch={"publisher": {"name": "x"}})


def test_write_metadata_rejects_unknown_format(tmp_cbz: Path) -> None:
    with pytest.raises(WriteValidationError, match="Unknown format"):
        write_metadata(
            tmp_cbz, patch={"publisher": {"name": "x"}}, formats=["not_a_format"]
        )


# --- bulk_write --------------------------------------------------------------


def test_bulk_write_yields_per_file_results(tmp_path: Path) -> None:
    """bulk_write emits one WriteResult per item."""
    items = []
    for i in range(3):
        target = tmp_path / f"f{i}.cbz"
        shutil.copy(CIX_CBZ_SOURCE_PATH, target)
        items.append(
            BulkWriteItem(
                path=target,
                patch={"publisher": {"name": f"Pub{i}"}},
                mode="replace",
                formats=frozenset({"COMICBOX_JSON"}),
            )
        )
    results = list(bulk_write(items))
    assert len(results) == 3
    assert all(r.written for r in results)
    # Each comic now has the correct publisher name.
    by_name = {r.path: _read_publisher(r.path)["name"] for r in results}
    for i in range(3):
        assert by_name[tmp_path / f"f{i}.cbz"] == f"Pub{i}"


def test_bulk_write_emits_events(tmp_cbz: Path) -> None:
    """on_event fires BatchStarted, FileParsed, BatchFinished."""
    items = [
        BulkWriteItem(
            path=tmp_cbz,
            patch={"publisher": {"name": "X"}},
            mode="replace",
            formats=frozenset({"COMICBOX_JSON"}),
        )
    ]
    events: list[Event] = []
    list(bulk_write(items, on_event=events.append))
    assert isinstance(events[0], BatchStarted)
    assert events[0].total == 1
    assert any(isinstance(e, FileParsed) for e in events)
    finished = events[-1]
    assert isinstance(finished, BatchFinished)
    assert finished.parsed == 1
    assert finished.errored == 0


def test_bulk_write_respects_cancel_token(tmp_path: Path) -> None:
    """Cancelling before submit means no items run."""
    items = []
    for i in range(3):
        target = tmp_path / f"f{i}.cbz"
        shutil.copy(CIX_CBZ_SOURCE_PATH, target)
        items.append(
            BulkWriteItem(
                path=target,
                patch={"publisher": {"name": "x"}},
                mode="replace",
                formats=frozenset({"COMICBOX_JSON"}),
            )
        )
    cancel = threading.Event()
    cancel.set()
    results = list(bulk_write(items, cancel=cancel))
    assert results == []


def test_bulk_write_reports_per_file_errors(tmp_path: Path) -> None:
    """A bad file in the batch produces a WriteResult.error, others succeed."""
    bad = tmp_path / "bad.cbz"
    bad.write_bytes(b"not a zip")
    good = tmp_path / "good.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, good)
    items = [
        BulkWriteItem(
            path=bad,
            patch={"publisher": {"name": "x"}},
            mode="replace",
            formats=frozenset({"COMICBOX_JSON"}),
        ),
        BulkWriteItem(
            path=good,
            patch={"publisher": {"name": "y"}},
            mode="replace",
            formats=frozenset({"COMICBOX_JSON"}),
        ),
    ]
    results = list(bulk_write(items))
    assert len(results) == 2
    by_path = {r.path: r for r in results}
    assert by_path[bad].error is not None
    assert by_path[good].written is True
