"""Parallel processing for large-scale comic metadata reading."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping

    from confuse.templates import AttrDict


def _read_one(
    path: Path | str,
    config: Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
) -> dict:
    """Read metadata from a single comic file."""
    with Comicbox(path, config=config) as cb:
        return cb.to_dict(fmt)


def iter_process_files(
    paths: Iterable[Path | str],
    config: AttrDict | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
) -> Generator[tuple[Path, dict], None, None]:
    """
    Yield (path, metadata_dict) as each file completes processing.

    Uses ProcessPoolExecutor with as_completed() so results stream back
    as fast as workers finish, regardless of submission order. Callers
    can track progress, abort with break, or batch updates as needed.

    Args:
        paths: Iterable of comic archive paths.
        config: Pre-built config (AttrDict or dict). Passed to each worker.
        fmt: Output metadata format.
        max_workers: Max worker processes. Defaults to CPU count.

    Yields:
        (Path, dict) tuples — path and its metadata (empty dict on failure).

    """
    config_dict: dict | None = dict(config) if config else None
    path_list = [Path(p) for p in paths]

    executor = ProcessPoolExecutor(max_workers=max_workers)
    try:
        futures = {
            executor.submit(_read_one, path, config_dict, fmt): path
            for path in path_list
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                yield path, future.result()
            except Exception:
                yield path, {}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def process_files(
    paths: Iterable[Path | str],
    config: AttrDict | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
) -> dict[Path, dict]:
    """
    Process multiple comic files in parallel with ProcessPoolExecutor.

    Args:
        paths: Iterable of comic archive paths.
        config: Pre-built config (AttrDict or dict). Passed to each worker.
        fmt: Output metadata format.
        max_workers: Max worker processes. Defaults to CPU count.

    Returns:
        Dict mapping each Path to its metadata dict.

    """
    return dict(iter_process_files(paths, config, fmt, max_workers))


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
