"""Tests for comicbox.process parallel metadata readers."""

from __future__ import annotations

import asyncio
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile

import pytest

from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.process import (
    _read_one,
    aread_metadata,
    iter_process_files,
    process_files,
)
from tests.const import (
    CB7_SOURCE_PATH,
    CIX_CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    EMPTY_CBZ_SOURCE_PATH,
    PDF_SOURCE_PATH,
)

CONFIG = get_config(Namespace(comicbox=Namespace(compute_page_count=True)))
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
FUTURE = datetime(2999, 1, 1, tzinfo=timezone.utc)
_CIX_CBZ_PAGES = 36

FIXTURES = (
    (CIX_CBZ_SOURCE_PATH, "CBZ", _CIX_CBZ_PAGES),
    (CIX_CBI_CBR_SOURCE_PATH, "CBR", 36),
    (CIX_CBT_SOURCE_PATH, "CBT", 5),
    (CB7_SOURCE_PATH, "CB7", 5),
    (PDF_SOURCE_PATH, "PDF", 4),
)


# --- _read_one --------------------------------------------------------------


@pytest.mark.parametrize(("path", "file_type", "page_count"), FIXTURES)
def test_read_one_full_metadata(path: Path, file_type: str, page_count: int) -> None:
    """Full metadata read returns envelope fields and a populated tags dict."""
    result = _read_one(path, config=CONFIG)
    assert result["file_type"] == file_type
    assert result["page_count"] == page_count
    # Full reads of Captain Science archives surface series info.
    assert result["tags"] is not None
    if file_type != "PDF":
        assert "series" in result["tags"]


def test_read_one_mtime_skip() -> None:
    """old_mtime in the future => tags=None but envelope still populated."""
    result = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, old_mtime=FUTURE)
    assert result["file_type"] == "CBZ"
    assert result["page_count"] is not None
    assert result["tags"] is None


def test_read_one_mtime_stale() -> None:
    """old_mtime at epoch => archive is newer, do a full read."""
    result = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, old_mtime=EPOCH)
    assert result["file_type"] == "CBZ"
    assert result["tags"] is not None
    assert "series" in result["tags"]


def test_read_one_no_full_metadata() -> None:
    """full_metadata=False => tags=None, envelope still populated."""
    result = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, full_metadata=False)
    assert result["file_type"] == "CBZ"
    assert result["page_count"] == _CIX_CBZ_PAGES
    assert result["tags"] is None


def test_read_one_empty_archive() -> None:
    """Empty cbz still returns envelope fields and a tags dict."""
    result = _read_one(EMPTY_CBZ_SOURCE_PATH, config=CONFIG)
    assert result["file_type"] == "CBZ"
    assert result["page_count"] == 0
    assert result["tags"] is not None


def test_read_one_envelope_strips_dupes_from_tags() -> None:
    """Envelope keys are removed from the tags dict so callers see one source."""
    result = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG)
    assert result["tags"] is not None
    assert "metadata_mtime" not in result["tags"]
    assert "page_count" not in result["tags"]
    assert "file_type" not in result["tags"]


# --- iter_process_files -----------------------------------------------------


def test_iter_process_files_basic() -> None:
    """Each path yields (path, (ReadResult, None))."""
    paths = [p for p, _, _ in FIXTURES]
    results = dict(iter_process_files(paths, config=CONFIG, max_workers=2))
    assert set(results) == set(paths)
    for path, _, page_count in FIXTURES:
        result, exc = results[path]
        assert exc is None
        assert result["page_count"] == page_count


def test_iter_process_files_bad_path_is_yielded_not_raised(
    tmp_path: Path,
) -> None:
    """A broken archive yields an exception, good paths still succeed."""
    bad = tmp_path / "broken.cbz"
    bad.write_bytes(b"not a zipfile")
    paths = [CIX_CBZ_SOURCE_PATH, bad]

    results = dict(iter_process_files(paths, config=CONFIG, max_workers=2))

    good_result, good_exc = results[CIX_CBZ_SOURCE_PATH]
    assert good_exc is None
    assert good_result["file_type"] == "CBZ"

    bad_result, bad_exc = results[bad]
    # Empty sentinel: every field is None on failure.
    assert bad_result["tags"] is None
    assert bad_result["file_type"] is None
    assert bad_result["page_count"] is None
    assert isinstance(bad_exc, (BadZipFile, OSError, Exception))


def test_iter_process_files_missing_file(tmp_path: Path) -> None:
    """A nonexistent path yields an OSError rather than raising."""
    missing = tmp_path / "does_not_exist.cbz"
    results = dict(iter_process_files([missing], config=CONFIG, max_workers=1))
    result, exc = results[missing]
    assert result["tags"] is None
    assert result["file_type"] is None
    assert exc is not None


def test_iter_process_files_empty_input() -> None:
    """Empty iterable => empty dict, no executor errors."""
    results = dict(iter_process_files([], config=CONFIG))
    assert results == {}


def test_iter_process_files_early_break_shuts_down() -> None:
    """Breaking out of the generator should not deadlock."""
    paths = [p for p, _, _ in FIXTURES]
    gen = iter_process_files(paths, config=CONFIG, max_workers=2)
    first = next(gen)
    assert first[0] in paths
    gen.close()  # triggers finally: executor.shutdown(cancel_futures=True)


def test_iter_process_files_mtime_map_skips_full_read() -> None:
    """old_mtime_map entry in the future => tags=None, envelope populated."""
    path = CIX_CBZ_SOURCE_PATH
    mtime_map = {str(path): FUTURE}
    results = dict(
        iter_process_files(
            [path], config=CONFIG, max_workers=1, old_mtime_map=mtime_map
        )
    )
    result, exc = results[path]
    assert exc is None
    assert result["file_type"] == "CBZ"
    assert result["tags"] is None


def test_iter_process_files_full_metadata_false() -> None:
    """full_metadata=False => tags=None, envelope populated."""
    paths = [CIX_CBZ_SOURCE_PATH]
    results = dict(
        iter_process_files(paths, config=CONFIG, max_workers=1, full_metadata=False)
    )
    result, exc = results[CIX_CBZ_SOURCE_PATH]
    assert exc is None
    assert result["file_type"] == "CBZ"
    assert result["tags"] is None


def test_iter_process_files_accepts_str_paths() -> None:
    """String paths are coerced to Path keys."""
    results = dict(
        iter_process_files([str(CIX_CBZ_SOURCE_PATH)], config=CONFIG, max_workers=1)
    )
    assert Path(CIX_CBZ_SOURCE_PATH) in results


def test_iter_process_files_with_worker_log_config() -> None:
    """A picklable log config dict is accepted and workers still produce results."""
    log_config = {
        "level": "WARNING",
        "format": "{time} | {level} | {message}",
        "sink": "stderr",
    }
    paths = [CIX_CBZ_SOURCE_PATH, CB7_SOURCE_PATH]
    results = dict(
        iter_process_files(
            paths, config=CONFIG, max_workers=2, worker_log_config=log_config
        )
    )
    assert set(results) == {Path(p) for p in paths}
    for result, exc in results.values():
        assert exc is None
        assert result["file_type"] in {"CBZ", "CB7"}


# --- process_files ----------------------------------------------------------


def test_process_files_returns_dict() -> None:
    """process_files is the dict() wrapper around iter_process_files."""
    paths = [CIX_CBZ_SOURCE_PATH, CB7_SOURCE_PATH]
    results = process_files(paths, config=CONFIG, max_workers=2)
    assert isinstance(results, dict)
    assert set(results) == {Path(p) for p in paths}
    for result, exc in results.values():
        assert exc is None
        assert result["file_type"] in {"CBZ", "CB7"}


def test_process_files_empty() -> None:
    """Empty input => empty dict."""
    assert process_files([], config=CONFIG) == {}


# --- aread_metadata ---------------------------------------------------------


def test_aread_metadata_returns_metadata() -> None:
    """Async read returns a populated ReadResult."""
    result = asyncio.run(aread_metadata(CIX_CBZ_SOURCE_PATH, config=CONFIG))
    assert result["file_type"] == "CBZ"
    assert result["page_count"] == _CIX_CBZ_PAGES


def test_aread_metadata_passes_fmt() -> None:
    """Fmt is forwarded positionally without being confused with logger."""
    result = asyncio.run(
        aread_metadata(
            CIX_CBZ_SOURCE_PATH, config=CONFIG, fmt=MetadataFormats.COMICBOX_YAML
        )
    )
    assert result["file_type"] == "CBZ"
