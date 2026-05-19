"""Parallel processing for large-scale comic metadata reading."""

from __future__ import annotations

import asyncio
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed
from functools import cache
from pathlib import Path
from tarfile import TarError
from typing import TYPE_CHECKING, Any, TypedDict
from zipfile import BadZipFile, LargeZipFile

from comicbox.box import Comicbox
from comicbox.box.archive.filenames import EPOCH_START
from comicbox.events import (
    BatchFinished,
    BatchStarted,
    FileError,
    FileParsed,
    FileShortCircuited,
)
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import MetadataFormats

if TYPE_CHECKING:
    import datetime
    from collections.abc import Generator, Iterable, Mapping

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import EventHandler


@cache
def _archive_errors() -> tuple[type[BaseException], ...]:
    """Return the tuple of archive errors, deferring py7zr / rarfile imports."""
    from py7zr.exceptions import ArchiveError as Py7zError
    from rarfile import Error as RarError

    return (
        UnsupportedArchiveTypeError,
        BadZipFile,
        LargeZipFile,
        RarError,
        Py7zError,
        TarError,
        OSError,
    )


class ReadResult(TypedDict):
    """
    Result of reading metadata from a single comic archive.

    The envelope fields (``metadata_mtime``, ``page_count``, ``file_type``)
    are populated cheaply on every successful read and are the source of
    truth for archive-level state tracking. ``tags`` carries the parsed
    metadata payload and is ``None`` when extraction was skipped — either
    because the embedded metadata mtime hadn't advanced past ``old_mtime``
    or because the caller passed ``full_metadata=False``.

    Distinguishing "skip" from "extracted-but-empty" is the contract that
    lets callers preserve existing tag links when the archive's tags
    haven't changed; an empty ``{}`` would mean "extracted, no tags
    found", which would force the caller to clear those links.
    """

    metadata_mtime: datetime.datetime | None
    page_count: int | None
    file_type: str | None
    tags: dict[str, Any] | None


def _empty_read_result() -> ReadResult:
    """Sentinel returned for archives that failed to open at all."""
    return ReadResult(
        metadata_mtime=None,
        page_count=None,
        file_type=None,
        tags=None,
    )


def _read_one(
    path: Path | str,
    config: ComicboxSettings | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    old_mtime: datetime.datetime | None = None,
    *,
    full_metadata: bool = True,
) -> ReadResult:
    """Read metadata from a single comic file (runs in a worker process)."""
    tags: dict[str, Any] | None = None
    metadata_mtime: datetime.datetime | None = None
    with Comicbox(path, config=config, fmt=fmt) as cb:
        if full_metadata:
            metadata_mtime = cb.get_metadata_mtime()
            if not old_mtime or not metadata_mtime or metadata_mtime > old_mtime:
                tags = cb.to_dict().get("comicbox", {})
                # Envelope fields are returned out-of-band; strip any
                # duplicates from the tag payload so callers see one
                # source of truth.
                if tags:
                    tags.pop("metadata_mtime", None)
                    tags.pop("page_count", None)
                    tags.pop("file_type", None)
        page_count = cb.get_page_count()
        file_type = cb.get_file_type()
    return ReadResult(
        metadata_mtime=metadata_mtime,
        page_count=page_count,
        file_type=file_type,
        tags=tags,
    )


def _collect_result(
    future: Any,
    path: Path,
    logger: Any,
) -> tuple[ReadResult, BaseException | None, bool]:
    """Collect one completed future; return (result, exception, pool_broken)."""
    try:
        return future.result(), None, False
    except _archive_errors() as exc:
        logger.warning(f"Failed to import {path}: {exc}")
        return _empty_read_result(), exc, False
    except BrokenExecutor as exc:
        logger.exception(f"Worker pool broken while processing {path}")
        return _empty_read_result(), exc, True
    except Exception as exc:
        logger.exception(f"Failed to import: {path}")
        return _empty_read_result(), exc, False


def _worker_log_init(log_config: Mapping) -> None:
    """
    Re-initialize loguru in a worker process from a picklable config dict.

    Recognized keys: "level", "format", "sink" ("stdout"|"stderr"|path string).
    """
    from comicbox.logger import init_logging

    init_logging(
        loglevel=log_config.get("level", "INFO"),
        log_format=log_config.get("format"),
        sink=log_config.get("sink"),
    )


_OutcomeCounters = dict[str, int]


def _classify_outcome(result: ReadResult, exc: BaseException | None) -> str:
    """One of: 'errored', 'short_circuited', 'parsed'."""
    if exc is not None:
        return "errored"
    if result["tags"] is None:
        # tags is None when the worker either hit the embedded-mtime
        # gate (metadata_mtime is set) or was asked for envelope-only
        # data via full_metadata=False (metadata_mtime is None).
        return "short_circuited"
    return "parsed"


def _emit_per_file_event(
    path: Path,
    *,
    index: int,
    total: int,
    result: ReadResult,
    exc: BaseException | None,
    on_event: EventHandler,
    counters: _OutcomeCounters,
) -> None:
    """Dispatch a single FileError / FileShortCircuited / FileParsed event."""
    outcome = _classify_outcome(result, exc)
    counters[outcome] += 1
    if outcome == "errored":
        assert exc is not None
        on_event(FileError(path=path, index=index, total=total, error=str(exc)))
    elif outcome == "short_circuited":
        reason = (
            "mtime_unchanged" if result["metadata_mtime"] is not None else "filtered"
        )
        on_event(FileShortCircuited(path=path, index=index, total=total, reason=reason))
    else:
        on_event(FileParsed(path=path, index=index, total=total))


def _iter_completed(
    futures: Mapping[Any, Path],
    logger: Any,
    on_event: EventHandler | None,
    total: int,
) -> Generator[tuple[Path, tuple[ReadResult, BaseException | None]], None, None]:
    """Yield results as futures complete; mark subsequent paths broken once the pool fails."""
    pool_broken = False
    counters: _OutcomeCounters = {"parsed": 0, "short_circuited": 0, "errored": 0}
    index = 0
    for future in as_completed(futures):
        path = futures[future]
        if pool_broken:
            exc = BrokenExecutor("Worker pool broken")
            counters["errored"] += 1
            if on_event is not None:
                on_event(FileError(path=path, index=index, total=total, error=str(exc)))
            yield path, (_empty_read_result(), exc)
            index += 1
            continue
        result, exc, broken = _collect_result(future, path, logger)
        if broken:
            pool_broken = True
        if on_event is not None:
            _emit_per_file_event(
                path,
                index=index,
                total=total,
                result=result,
                exc=exc,
                on_event=on_event,
                counters=counters,
            )
        yield path, (result, exc)
        index += 1
    if on_event is not None:
        on_event(
            BatchFinished(
                total=total,
                parsed=counters["parsed"],
                short_circuited=counters["short_circuited"],
                errored=counters["errored"],
            )
        )


def iter_process_files(  # noqa: PLR0913
    paths: Iterable[Path | str],
    config: ComicboxSettings | Mapping | None = None,
    logger: Any = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
    old_mtime_map: Mapping[str, datetime.datetime] | None = None,
    worker_log_config: Mapping | None = None,
    *,
    full_metadata: bool = True,
    on_event: EventHandler | None = None,
) -> Generator[tuple[Path, tuple[ReadResult, BaseException | None]], None, None]:
    """
    Yield (path, (ReadResult, exception_or_None)) as each file completes.

    All per-path failures — submit-time, worker-raised, or pool-broken —
    are delivered as the second element of the tuple rather than raised,
    so a single bad path cannot abort the whole run. On failure the
    ReadResult is the empty sentinel (all fields ``None``); inspect the
    exception, not the result, to detect failure.

    ``worker_log_config``: optional dict of ``{"level", "format", "sink"}``
        used to re-initialize loguru inside each worker so subprocess log
        output matches the caller's format. Must be picklable; pass sink
        as ``"stdout"`` / ``"stderr"`` / path string, not a file object.

    ``on_event``: optional handler invoked on the orchestrator thread with
        each :class:`comicbox.events.Event`. Fires :class:`BatchStarted`
        once before the first submit, one of :class:`FileParsed` /
        :class:`FileShortCircuited` / :class:`FileError` per delivered
        result, and :class:`BatchFinished` once with totals. Handler runs
        on the orchestrator thread and must be thread-safe and quick.
    """
    if not logger:
        from loguru import logger
    if not old_mtime_map:
        old_mtime_map = {}
    path_list = [Path(p) for p in paths]
    total = len(path_list)

    if on_event is not None:
        on_event(BatchStarted(total=total))

    executor_kwargs: dict[str, Any] = {"max_workers": max_workers}
    if worker_log_config:
        executor_kwargs["initializer"] = _worker_log_init
        executor_kwargs["initargs"] = (dict(worker_log_config),)
    executor = ProcessPoolExecutor(**executor_kwargs)
    try:
        futures: dict = {}
        submit_failures: list[tuple[Path, BaseException]] = []
        for path in path_list:
            old_mtime = old_mtime_map.get(str(path), EPOCH_START)
            try:
                future = executor.submit(
                    _read_one,
                    path,
                    config,
                    fmt,
                    old_mtime,
                    full_metadata=full_metadata,
                )
            except Exception as exc:
                logger.exception(f"Failed to submit {path}")
                submit_failures.append((path, exc))
                continue
            futures[future] = path

        # Surface submit-time failures up front so the index sequence in
        # events matches the yield order seen by the caller.
        for path, exc in submit_failures:
            if on_event is not None:
                on_event(FileError(path=path, error=str(exc)))
            yield path, (_empty_read_result(), exc)

        yield from _iter_completed(futures, logger, on_event, total)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def process_files(
    paths: Iterable[Path | str],
    config: ComicboxSettings | Mapping | None = None,
    logger: Any = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
    max_workers: int | None = None,
    worker_log_config: Mapping | None = None,
    *,
    on_event: EventHandler | None = None,
) -> dict[Path, tuple[ReadResult, BaseException | None]]:
    """Process multiple comic files in parallel via ProcessPoolExecutor."""
    return dict(
        iter_process_files(
            paths,
            config,
            logger,
            fmt,
            max_workers,
            worker_log_config=worker_log_config,
            on_event=on_event,
        )
    )


async def aread_metadata(
    path: Path | str,
    config: ComicboxSettings | Mapping | None = None,
    fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
) -> ReadResult:
    """Read metadata from a single comic file in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_one, path, config, fmt)
