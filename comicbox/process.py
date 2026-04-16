"""Parallel processing for large-scale comic metadata reading."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from confuse.templates import AttrDict


def _read_one(
    path: Path | str,
    config: Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
) -> dict:
    """Read metadata from a single comic file."""
    with Comicbox(path, config=config) as cb:
        return cb.to_dict(fmt)


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
    # Convert config to a plain dict for pickling across processes
    config_dict: dict | None = dict(config) if config else None
    path_list = [Path(p) for p in paths]

    results: dict[Path, dict] = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_read_one, path, config_dict, fmt): path
            for path in path_list
        }
        for future in futures:
            path = futures[future]
            try:
                results[path] = future.result()
            except Exception:
                results[path] = {}
    return results


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
