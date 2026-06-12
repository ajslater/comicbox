"""
Public write API: single-file ``write_metadata`` and batch ``bulk_write``.

Wraps the existing ``Comicbox(...).dump()`` plumbing with a documented,
Codex-facing surface:

- ``mode``: ``"additive"`` / ``"update"`` / ``"replace"`` — picks the
  merge strategy applied to the patch dict against the comic's
  existing metadata. See :class:`comicbox.config.settings.WriteMode`.
- ``formats``: which on-archive formats to write back (ComicInfo.xml,
  comicbox.yaml, …). Names match the ``MetadataFormats`` enum value.
- ``dry_run``: return the would-be-written payload instead of touching
  the archive.

``bulk_write`` orchestrates the same call over many files via a process-
global ``ThreadPoolExecutor`` (writes are I/O bound — full archive
repack per CBZ). A module-level semaphore caps concurrent writes so a
big batch can't starve other disk traffic.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.config.settings import WriteMode
from comicbox.events import (
    BatchFinished,
    BatchStarted,
    FileError,
    FileParsed,
    FileShortCircuited,
)

# Historical import path for WriteValidationError; the definition lives in
# comicbox.exceptions so it shares the ComicboxError base without cycles.
from comicbox.exceptions import WriteValidationError as WriteValidationError
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator
    from pathlib import Path

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import EventHandler


Mode: TypeAlias = Literal["additive", "update", "replace"]
FormatName: TypeAlias = str  # Matches MetadataFormats.name; e.g. "COMIC_INFO".

# Module-level cap on concurrent writes across the process. CBZ writes
# fully repack the archive; running too many in parallel just contends
# on disk IO. Codex can bump this if its workload calls for it.
_MAX_CONCURRENT_WRITES = 8
_write_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT_WRITES)


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Per-file outcome of a write."""

    path: Path
    written: bool = False
    dry_run_payload: dict[str, str] | None = None
    error: BaseException | None = None
    # True when the batch was cancelled before this file's write started
    # (stop_on_error tripped, or the caller set the cancel event).
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class BulkWriteItem:
    """One unit of work for ``bulk_write``."""

    path: Path
    patch: Mapping[str, Any]
    mode: Mode = "additive"
    formats: frozenset[FormatName] | None = None


def write_metadata(
    path: Path,
    patch: Mapping[str, Any],
    *,
    mode: Mode = "additive",
    formats: Iterable[FormatName] | None = None,
    dry_run: bool = False,
    base_config: ComicboxSettings | None = None,
) -> WriteResult:
    """
    Write metadata to one comic archive.

    ``patch`` is a comicbox-shaped dict — either the contents *under* the
    ``"comicbox"`` root tag, or the root-wrapped form ``Comicbox.to_dict``
    returns (``{"comicbox": {...}}``); the wrapper is detected and
    unwrapped so the natural round-trip works.

    With ``dry_run=True`` no archive is touched; the result's
    ``dry_run_payload`` carries the serialized would-be-written content
    per requested format (keyed by format name).
    """
    patch = _unwrap_root_tag(patch)
    if not patch:
        msg = "write_metadata(): patch must be a non-empty mapping"
        raise WriteValidationError(msg)
    mode_enum = _validate_mode(mode)
    fmt_set = _resolve_formats(formats)
    settings = _build_write_settings(mode_enum, fmt_set, base_config=base_config)
    wrapped: dict[str, Any] = {ComicboxSchemaMixin.ROOT_TAG: dict(patch)}

    try:
        with Comicbox(path, config=settings, metadata=wrapped) as cb:
            if dry_run:
                payload = {fmt.name: cb.to_string(fmt) for fmt in fmt_set}
                return WriteResult(path=path, written=False, dry_run_payload=payload)
            cb.dump()
    except Exception as exc:
        return WriteResult(path=path, error=exc)
    return WriteResult(path=path, written=True)


def _run_bulk_write(
    pool: ThreadPoolExecutor,
    items: list[BulkWriteItem],
    *,
    window: int,
    base_config: ComicboxSettings | None,
    total: int,
    on_event: EventHandler | None,
    stop_on_error: bool,
    cancel: threading.Event | None,
) -> Iterator[tuple[WriteResult, bool]]:
    """
    Submit a bounded window of items, drain completions, refill.

    Draining leads submission so a tripped ``cancel`` event genuinely stops
    work: unsubmitted items are never handed to the pool and are yielded as
    cancelled results. Yields (result, ok) pairs.
    """
    queue = deque(enumerate(items))
    pending: dict[Future, tuple[int, BulkWriteItem]] = {}
    while pending or queue:
        if cancel is not None and cancel.is_set():
            yield from _flush_cancelled(queue)
        else:
            while queue and len(pending) < window:
                index, item = queue.popleft()
                future = pool.submit(_write_one, item, base_config, cancel)
                pending[future] = (index, item)
        if not pending:
            break
        yield from _drain_completed(
            pending,
            total=total,
            on_event=on_event,
            stop_on_error=stop_on_error,
            cancel=cancel,
        )


def _flush_cancelled(
    queue: deque[tuple[int, BulkWriteItem]],
) -> Iterator[tuple[WriteResult, bool]]:
    """Drain unsubmitted items as cancelled results."""
    while queue:
        _index, item = queue.popleft()
        yield WriteResult(path=item.path, cancelled=True), False


def _drain_completed(
    pending: dict[Future, tuple[int, BulkWriteItem]],
    *,
    total: int,
    on_event: EventHandler | None,
    stop_on_error: bool,
    cancel: threading.Event | None,
) -> Iterator[tuple[WriteResult, bool]]:
    """Wait for at least one completion; yield and signal cancel on error."""
    done, _running = wait(pending, return_when=FIRST_COMPLETED)
    for future in done:
        index, item = pending.pop(future)
        try:
            result = future.result()
        except Exception as exc:
            result = WriteResult(path=item.path, error=exc)
        if result.error is not None and stop_on_error and cancel is not None:
            cancel.set()
        ok = _emit_write_event(result, index, total, on_event)
        yield result, ok


def _emit_batch_finished(
    on_event: EventHandler | None, *, total: int, parsed: int, errored: int
) -> None:
    """No-op if no handler; else fire the per-batch summary event."""
    if on_event is None:
        return
    on_event(
        BatchFinished(
            total=total,
            parsed=parsed,
            short_circuited=0,
            errored=errored,
        )
    )


def bulk_write(
    items: Iterable[BulkWriteItem],
    *,
    workers: int | None = None,
    on_event: EventHandler | None = None,
    stop_on_error: bool = False,
    cancel: threading.Event | None = None,
    base_config: ComicboxSettings | None = None,
) -> Generator[WriteResult, None, None]:
    """
    Write metadata to many files in parallel.

    Returns an iterator that MUST be drained: writes are submitted in a
    bounded window as results are consumed, so discarding the iterator
    without iterating performs no writes. Input handling, the
    ``BatchStarted`` event, and pool creation happen eagerly at call
    time. Abandoning the iterator midway never blocks: queued writes are
    cancelled and in-flight ones finish in their worker threads.

    Yields :class:`WriteResult` per file in *completion* order, not
    submission order. Caller may pass a ``cancel`` :class:`threading.Event`;
    once set, no new writes start: in-flight writes run to completion and
    every queued file is reported with ``cancelled=True``. With
    ``stop_on_error=True`` the first failed write trips the same
    cancellation (an internal event is created if the caller didn't pass
    one). ``on_event`` receives the shared :class:`comicbox.events`
    stream (``BatchStarted`` / ``FileParsed`` / ``FileError`` /
    ``BatchFinished``); cancelled files emit no per-file event.
    """
    item_list = list(items)
    total = len(item_list)
    if stop_on_error and cancel is None:
        # stop_on_error signals through the cancel event; make one if the
        # caller didn't supply their own.
        cancel = threading.Event()
    if on_event is not None:
        on_event(BatchStarted(total=total))
    # Eager pool creation; its threads only spawn on first submit, so a
    # never-iterated iterator leaks nothing.
    pool = ThreadPoolExecutor(max_workers=workers)
    # Submission window matches the pool width so the pool stays saturated
    # while no item waits in the pool's internal queue beyond cancel's reach.
    window = workers or _MAX_CONCURRENT_WRITES
    return _drain_bulk_write(
        pool,
        item_list,
        window=window,
        base_config=base_config,
        total=total,
        on_event=on_event,
        stop_on_error=stop_on_error,
        cancel=cancel,
    )


def _drain_bulk_write(
    pool: ThreadPoolExecutor,
    items: list[BulkWriteItem],
    *,
    window: int,
    base_config: ComicboxSettings | None,
    total: int,
    on_event: EventHandler | None,
    stop_on_error: bool,
    cancel: threading.Event | None,
) -> Generator[WriteResult, None, None]:
    """Drain the bulk-write pipeline; owns the pool's lifecycle."""
    parsed = 0
    errored = 0
    try:
        for result, ok in _run_bulk_write(
            pool,
            items,
            window=window,
            base_config=base_config,
            total=total,
            on_event=on_event,
            stop_on_error=stop_on_error,
            cancel=cancel,
        ):
            if result.error is not None:
                errored += 1
            elif ok:
                parsed += 1
            yield result
    finally:
        # Never block here: on abandonment this runs from the generator's
        # close(), and waiting out queued CBZ repacks would stall the
        # caller's error handling. Mirrors iter_process_files.
        pool.shutdown(wait=False, cancel_futures=True)
        _emit_batch_finished(on_event, total=total, parsed=parsed, errored=errored)


def _emit_write_event(
    result: WriteResult,
    index: int,
    total: int,
    on_event: EventHandler | None,
) -> bool:
    """Pick + emit the right event for a result. Return True if it was a parse."""
    if result.cancelled:
        # Cancelled files never started; they get no per-file event.
        return False
    if on_event is None:
        return result.error is None and result.dry_run_payload is None
    if result.error is not None:
        on_event(
            FileError(
                path=result.path,
                index=index,
                total=total,
                error=str(result.error),
            )
        )
        return False
    if result.dry_run_payload is not None:
        # "dry_run", not "filtered": the latter is the read-workflow
        # meaning (caller passed full_metadata=False) and misled event
        # consumers matching on the shared stream.
        on_event(
            FileShortCircuited(
                path=result.path,
                index=index,
                total=total,
                reason="dry_run",
            )
        )
        return False
    on_event(FileParsed(path=result.path, index=index, total=total))
    return True


# --- internals --------------------------------------------------------------


def _unwrap_root_tag(patch: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Accept a root-wrapped patch (the exact shape ``Comicbox.to_dict`` returns).

    Without this, the wrapper key would be silently dropped as unknown by
    the schema and the write would no-op while reporting success.
    """
    if set(patch) == {ComicboxSchemaMixin.ROOT_TAG}:
        inner = patch[ComicboxSchemaMixin.ROOT_TAG]
        if isinstance(inner, Mapping):
            return inner
    return patch


def _write_one(
    item: BulkWriteItem,
    base_config: ComicboxSettings | None,
    cancel: threading.Event | None = None,
) -> WriteResult:
    """Per-thread worker. Acquires the global write semaphore."""
    with _write_semaphore:
        # Re-check after the semaphore wait: the batch may have been
        # cancelled while this item was queued behind other writes.
        if cancel is not None and cancel.is_set():
            return WriteResult(path=item.path, cancelled=True)
        return write_metadata(
            item.path,
            item.patch,
            mode=item.mode,
            formats=item.formats,
            base_config=base_config,
        )


def _validate_mode(mode: Mode) -> WriteMode:
    try:
        return WriteMode(mode)
    except ValueError as exc:
        msg = f"Unknown mode {mode!r}; expected one of {[m.value for m in WriteMode]}"
        raise WriteValidationError(msg) from exc


def _resolve_formats(
    formats: Iterable[FormatName] | None,
) -> frozenset[MetadataFormats]:
    """Convert a mixed iterable of names / enum values to MetadataFormats."""
    if not formats:
        msg = "write_metadata(): at least one format is required"
        raise WriteValidationError(msg)
    resolved: set[MetadataFormats] = set()
    for f in formats:
        if isinstance(f, MetadataFormats):
            resolved.add(f)
            continue
        try:
            resolved.add(MetadataFormats[str(f).upper()])
        except KeyError as exc:
            valid = ", ".join(m.name for m in MetadataFormats)
            msg = f"Unknown format {f!r}; expected one of: {valid}"
            raise WriteValidationError(msg) from exc
    return frozenset(resolved)


def _build_write_settings(
    mode: WriteMode,
    formats: frozenset[MetadataFormats],
    *,
    base_config: ComicboxSettings | None,
) -> ComicboxSettings:
    """Layer write.mode / write.formats over a base config."""
    base = base_config or get_config()
    # replace() carries every other WriteSettings field forward; the old
    # field-by-field copy silently reset any newly added field to its
    # default for every caller passing base_config.
    new_write = replace(base.write, formats=formats, mode=mode)
    return replace(base, write=new_write)
