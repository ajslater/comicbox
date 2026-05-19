"""Tests for the read-event stream emitted by iter_process_files()."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from comicbox.config import get_config
from comicbox.events import (
    BatchFinished,
    BatchStarted,
    Event,
    FileError,
    FileParsed,
    FileShortCircuited,
)
from comicbox.process import iter_process_files
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = get_config(Namespace(comicbox=Namespace(compute_page_count=True)))
FUTURE = datetime(2999, 1, 1, tzinfo=timezone.utc)


def _drain(gen) -> None:
    for _ in gen:
        pass


def test_on_event_fires_batch_started_and_finished() -> None:
    """BatchStarted up-front, BatchFinished at the end, with totals."""
    events: list[Event] = []
    _drain(
        iter_process_files([CIX_CBZ_SOURCE_PATH], config=CONFIG, on_event=events.append)
    )
    assert isinstance(events[0], BatchStarted)
    assert events[0].total == 1
    assert isinstance(events[-1], BatchFinished)
    assert events[-1].total == 1
    assert events[-1].parsed + events[-1].short_circuited + events[-1].errored == 1


def test_on_event_emits_file_parsed_when_metadata_changed() -> None:
    """Full parse emits FileParsed with index/total."""
    events: list[Event] = []
    _drain(
        iter_process_files([CIX_CBZ_SOURCE_PATH], config=CONFIG, on_event=events.append)
    )
    parsed = [e for e in events if isinstance(e, FileParsed)]
    assert len(parsed) == 1
    assert parsed[0].path == CIX_CBZ_SOURCE_PATH
    assert parsed[0].index == 0
    assert parsed[0].total == 1


def test_on_event_emits_file_short_circuited_on_mtime_gate() -> None:
    """When old_mtime is in the future, the worker skips parse."""
    events: list[Event] = []
    _drain(
        iter_process_files(
            [CIX_CBZ_SOURCE_PATH],
            config=CONFIG,
            old_mtime_map={str(CIX_CBZ_SOURCE_PATH): FUTURE},
            on_event=events.append,
        )
    )
    short = [e for e in events if isinstance(e, FileShortCircuited)]
    assert len(short) == 1
    assert short[0].reason == "mtime_unchanged"
    assert short[0].path == CIX_CBZ_SOURCE_PATH


def test_on_event_emits_filtered_when_full_metadata_false() -> None:
    """full_metadata=False means envelope-only; tags=None with no mtime → 'filtered'."""
    events: list[Event] = []
    _drain(
        iter_process_files(
            [CIX_CBZ_SOURCE_PATH],
            config=CONFIG,
            on_event=events.append,
            full_metadata=False,
        )
    )
    short = [e for e in events if isinstance(e, FileShortCircuited)]
    assert len(short) == 1
    assert short[0].reason == "filtered"


def test_on_event_emits_file_error_for_bad_archive(tmp_path: Path) -> None:
    """Submit-time / worker-time failures surface as FileError."""
    bad = tmp_path / "not-a-comic.cbz"
    bad.write_bytes(b"not a zip")
    events: list[Event] = []
    _drain(iter_process_files([bad], config=CONFIG, on_event=events.append))
    errors = [e for e in events if isinstance(e, FileError)]
    assert len(errors) == 1
    assert errors[0].path == bad
    assert errors[0].error  # non-empty
    finished = events[-1]
    assert isinstance(finished, BatchFinished)
    assert finished.errored == 1


def test_on_event_optional_keeps_legacy_behavior() -> None:
    """No on_event passed: legacy stream still yields path/result tuples."""
    out = list(iter_process_files([CIX_CBZ_SOURCE_PATH], config=CONFIG))
    assert len(out) == 1
    path, (result, exc) = out[0]
    assert path == CIX_CBZ_SOURCE_PATH
    assert exc is None
    assert result["tags"] is not None
