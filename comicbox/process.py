"""Parallel processing for large-scale comic metadata reading."""

from __future__ import annotations

import asyncio
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed
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

_ARCHIVE_ERRORS: tuple[type[BaseException], ...] = (
    UnsupportedArchiveTypeError,
    BadZipFile,
    LargeZipFile,
    RarError,
    Py7zError,
    TarError,
    OSError,
)


def _read_one(
    path: Path | str,
    config: Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    old_mtime: datetime.datetime | None = None,
    *,
    full_metadata: bool = True,
) -> dict[str, Any]:
    """Read metadata from a single comic file (runs in a worker process)."""
    md: dict[str, Any] = {}
    with Comicbox(path, config=config, fmt=fmt) as cb:
        if full_metadata:
            if not old_mtime:
                md = cb.to_dict()
                md = md.get("comicbox", {})
            else:
                new_md_mtime = cb.get_metadata_mtime()
                if not new_md_mtime or new_md_mtime > old_mtime:
                    md = cb.to_dict()
                    md = md.get("comicbox", {})
                md["metadata_mtime"] = new_md_mtime
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
) -> Generator[tuple[Path, tuple[dict, BaseException | None]], None, None]:
    """
    Yield (path, (metadata_dict, exception_or_None)) as each file completes.

    All per-path failures — submit-time, worker-raised, or pool-broken —
    are delivered as the second element of the tuple rather than raised,
    so a single bad path cannot abort the whole run.
    """
    if not logger:
        from loguru import logger
    if not old_mtime_map:
        old_mtime_map = {}
    config_dict: dict | None = dict(config) if config else None
    path_list = [Path(p) for p in paths]

    executor = ProcessPoolExecutor(max_workers=max_workers)
    try:
        futures: dict = {}
        for path in path_list:
            # Dispatch read job
            old_mtime = old_mtime_map.get(str(path), EPOCH_START)
            try:
                future = executor.submit(
                    _read_one,
                    path,
                    config_dict,
                    fmt,
                    old_mtime,
                    full_metadata=full_metadata,
                )
            except Exception as exc:
                logger.exception(f"Failed to submit {path}")
                yield path, ({}, exc)
                continue
            futures[future] = path

        pool_broken = False
        for future in as_completed(futures):
            # Collect result of read job
            path = futures[future]
            if pool_broken:
                yield path, ({}, BrokenExecutor("Worker pool broken"))
                continue
            try:
                yield path, (future.result(), None)
            except _ARCHIVE_ERRORS as exc:
                logger.warning(f"Failed to import {path}: {exc}")
                yield path, ({}, exc)
            except BrokenExecutor as exc:
                logger.exception(f"Worker pool broken while processing {path}")
                yield path, ({}, exc)
                pool_broken = True
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
) -> dict[Path, tuple[dict, BaseException | None]]:
    """Process multiple comic files in parallel via ProcessPoolExecutor."""
    return dict(iter_process_files(paths, config, logger, fmt, max_workers))


async def aread_metadata(
    path: Path | str,
    config: AttrDict | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
) -> dict:
    """Read metadata from a single comic file in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_one, path, config, fmt)
