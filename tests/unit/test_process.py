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
    """Full metadata read returns file_type, page_count, and comicbox fields."""
    md = _read_one(path, config=CONFIG)
    assert md["file_type"] == file_type
    assert md["page_count"] == page_count
    # Full reads of Captain Science archives surface series info.
    if file_type != "PDF":
        assert "series" in md


def test_read_one_mtime_skip() -> None:
    """old_mtime in the future => skip full read, only return minimal fields."""
    md = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, old_mtime=FUTURE)
    assert md["file_type"] == "CBZ"
    assert "page_count" in md
    assert "series" not in md


def test_read_one_mtime_stale() -> None:
    """old_mtime at epoch => archive is newer, do a full read."""
    md = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, old_mtime=EPOCH)
    assert md["file_type"] == "CBZ"
    assert "series" in md


def test_read_one_no_full_metadata() -> None:
    """full_metadata=False => only page_count + file_type."""
    md = _read_one(CIX_CBZ_SOURCE_PATH, config=CONFIG, full_metadata=False)
    assert md["file_type"] == "CBZ"
    assert md["page_count"] == _CIX_CBZ_PAGES
    assert "series" not in md
    assert "notes" not in md


def test_read_one_empty_archive() -> None:
    """Empty cbz still returns a file_type and zero pages."""
    md = _read_one(EMPTY_CBZ_SOURCE_PATH, config=CONFIG)
    assert md["file_type"] == "CBZ"
    assert md["page_count"] == 0


# --- iter_process_files -----------------------------------------------------


def test_iter_process_files_basic() -> None:
    """Each path yields (path, (dict, None))."""
    paths = [p for p, _, _ in FIXTURES]
    results = dict(iter_process_files(paths, config=CONFIG, max_workers=2))
    assert set(results) == set(paths)
    for path, _, page_count in FIXTURES:
        md, exc = results[path]
        assert exc is None
        assert md["page_count"] == page_count


def test_iter_process_files_bad_path_is_yielded_not_raised(
    tmp_path: Path,
) -> None:
    """A broken archive yields an exception, good paths still succeed."""
    bad = tmp_path / "broken.cbz"
    bad.write_bytes(b"not a zipfile")
    paths = [CIX_CBZ_SOURCE_PATH, bad]

    results = dict(iter_process_files(paths, config=CONFIG, max_workers=2))

    good_md, good_exc = results[CIX_CBZ_SOURCE_PATH]
    assert good_exc is None
    assert good_md["file_type"] == "CBZ"

    bad_md, bad_exc = results[bad]
    assert bad_md == {}
    assert isinstance(bad_exc, (BadZipFile, OSError, Exception))


def test_iter_process_files_missing_file(tmp_path: Path) -> None:
    """A nonexistent path yields an OSError rather than raising."""
    missing = tmp_path / "does_not_exist.cbz"
    results = dict(iter_process_files([missing], config=CONFIG, max_workers=1))
    md, exc = results[missing]
    assert md == {}
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
    """old_mtime_map entry in the future => minimal metadata only."""
    path = CIX_CBZ_SOURCE_PATH
    mtime_map = {str(path): FUTURE}
    results = dict(
        iter_process_files(
            [path], config=CONFIG, max_workers=1, old_mtime_map=mtime_map
        )
    )
    md, exc = results[path]
    assert exc is None
    assert md["file_type"] == "CBZ"
    assert "series" not in md


def test_iter_process_files_full_metadata_false() -> None:
    """full_metadata=False keyword => only page_count + file_type per path."""
    paths = [CIX_CBZ_SOURCE_PATH]
    results = dict(
        iter_process_files(paths, config=CONFIG, max_workers=1, full_metadata=False)
    )
    md, exc = results[CIX_CBZ_SOURCE_PATH]
    assert exc is None
    assert md["file_type"] == "CBZ"
    assert "series" not in md


def test_iter_process_files_accepts_str_paths() -> None:
    """String paths are coerced to Path keys."""
    results = dict(
        iter_process_files([str(CIX_CBZ_SOURCE_PATH)], config=CONFIG, max_workers=1)
    )
    assert Path(CIX_CBZ_SOURCE_PATH) in results


# --- process_files ----------------------------------------------------------


def test_process_files_returns_dict() -> None:
    """process_files is the dict() wrapper around iter_process_files."""
    paths = [CIX_CBZ_SOURCE_PATH, CB7_SOURCE_PATH]
    results = process_files(paths, config=CONFIG, max_workers=2)
    assert isinstance(results, dict)
    assert set(results) == {Path(p) for p in paths}
    for md, exc in results.values():
        assert exc is None
        assert md["file_type"] in {"CBZ", "CB7"}


def test_process_files_empty() -> None:
    """Empty input => empty dict."""
    assert process_files([], config=CONFIG) == {}


# --- aread_metadata ---------------------------------------------------------


def test_aread_metadata_returns_metadata() -> None:
    """Async read returns a populated metadata dict."""
    md = asyncio.run(aread_metadata(CIX_CBZ_SOURCE_PATH, config=CONFIG))
    assert md["file_type"] == "CBZ"
    assert md["page_count"] == _CIX_CBZ_PAGES


def test_aread_metadata_passes_fmt() -> None:
    """Fmt is forwarded positionally without being confused with logger."""
    md = asyncio.run(
        aread_metadata(
            CIX_CBZ_SOURCE_PATH, config=CONFIG, fmt=MetadataFormats.COMICBOX_YAML
        )
    )
    assert md["file_type"] == "CBZ"
