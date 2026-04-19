"""Parallel processing for large-scale comic metadata reading."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from tarfile import TarError
from typing import TYPE_CHECKING, Any
from zipfile import BadZipFile, LargeZipFile

from py7zr.exceptions import ArchiveError as Py7zError
from rarfile import Error as RarError

from comicbox.box import Comicbox
from comicbox.box.archive.filenames import EPOCH_START
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import MetadataFormats

if TYPE_CHECKING:
    import datetime
    from collections.abc import Generator, Iterable, Mapping

    from confuse.templates import AttrDict


def _read_one(
    path: Path | str,
    config: Mapping | None = None,
    logger: Any = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    old_mtime: datetime.datetime | None = None,
    *,
    full_metadata: bool = True,
) -> dict[str, Any]:
    """Read metadata from a single comic file."""
    md: dict[str, Any] = {}
    with Comicbox(path, config=config, logger=logger, fmt=fmt) as cb:
        if full_metadata:
            if not old_mtime:
                md = cb.to_dict()
                md = md.get("comicbox", {})
            else:
                new_md_mtime = cb.get_metadata_mtime()
                if not new_md_mtime or new_md_mtime > old_mtime:
                    md = cb.to_dict()
                    md = md.get("comicbox", {})
        if "page_count" not in md:
            md["page_count"] = cb.get_page_count()
        md["file_type"] = cb.get_file_type()
    return md


def iter_process_files(
    paths: Iterable[Path | str],
    config: AttrDict | Mapping | None = None,
    logger: Any = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
    old_mtime_map: Mapping[str, datetime.datetime] | None = None,
    *,
    full_metadata: bool = True,
) -> Generator[tuple[Path, tuple[dict, Exception | None]], None, None]:
    """
    Yield (path, metadata_dict) as each file completes processing.

    Uses ProcessPoolExecutor with as_completed() so results stream back
    as fast as workers finish, regardless of submission order. Callers
    can track progress, abort with break, or batch updates as needed.

    Args:
        paths: Iterable of comic archive paths.
        config: Pre-built config (AttrDict or dict). Passed to each worker.
        logger: external logger for comicbox to use.
        fmt: Output metadata format.
        max_workers: Max worker processes. Defaults to CPU count.
        old_mtime_map: Map of paths to old mtimes for skipping full metadata extraction.
        full_metadata: Whether to extract full metadata or just page_count and file_type.

    Yields:
        (Path, dict) tuples — path and its metadata (empty dict on failure).

    """
    if not logger:
        from loguru import logger
    if not old_mtime_map:
        old_mtime_map = {}
    config_dict: dict | None = dict(config) if config else None
    path_list = [Path(p) for p in paths]

    executor = ProcessPoolExecutor(max_workers=max_workers)
    try:
        futures = {}
        for path in path_list:
            old_mtime = old_mtime_map.get(str(path), EPOCH_START)
            future = executor.submit(
                _read_one,
                path,
                config_dict,
                logger,
                fmt,
                full_metadata=full_metadata,
                old_mtime=old_mtime,
            )
            futures[future] = path
        for future in as_completed(futures):
            path = futures[future]
            try:
                yield path, (future.result(), None)
            except (
                UnsupportedArchiveTypeError,
                BadZipFile,
                LargeZipFile,
                RarError,
                Py7zError,
                TarError,
                OSError,
            ) as exc:
                logger.warning(f"Failed to import {path}: {exc}")
                yield path, ({}, exc)
            except Exception as exc:
                logger.exception(f"Failed to import: {path}")
                yield path, ({}, exc)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def process_files(
    paths: Iterable[Path | str],
    config: AttrDict | Mapping | None = None,
    logger: Any = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
) -> dict[Path, tuple[dict, Exception | None]]:
    """
    Process multiple comic files in parallel with ProcessPoolExecutor.

    Args:
        paths: Iterable of comic archive paths.
        config: Pre-built config (AttrDict or dict). Passed to each worker.
        logger: external logger for comicbox to use.
        fmt: Output metadata format.
        max_workers: Max worker processes. Defaults to CPU count.

    Returns:
        Dict mapping each Path to its metadata dict.

    """
    return dict(iter_process_files(paths, config, logger, fmt, max_workers))


async def aread_metadata(
    path: Path | str,
    config: AttrDict | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
) -> dict:
    """
    Read metadata from a single comic file in a thread executor.

    For async integration (e.g., Django/Codex). Runs the synchronous
    Comicbox read in the default thread pool executor.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_one, path, config, fmt)
