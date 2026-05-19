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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.config.settings import WriteMode, WriteSettings
from comicbox.events import (
    BatchFinished,
    BatchStarted,
    FileError,
    FileParsed,
    FileShortCircuited,
)
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping
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


class WriteValidationError(Exception):
    """Raised when write_metadata inputs are inconsistent or invalid."""


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Per-file outcome of a write."""

    path: Path
    written: bool = False
    dry_run_payload: dict[str, str] | None = None
    error: BaseException | None = None


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

    ``patch`` is a comicbox-shaped dict (the same shape ``Comicbox.to_dict``
    returns under the ``"comicbox"`` root); it is wrapped in ``{"comicbox": …}``
    before being layered onto the merge pipeline.

    With ``dry_run=True`` no archive is touched; the result's
    ``dry_run_payload`` carries the serialized would-be-written content
    per requested format (keyed by format name).
    """
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


def bulk_write(
    items: Iterable[BulkWriteItem],
    *,
    workers: int | None = None,
    on_event: EventHandler | None = None,
    stop_on_error: bool = False,
    cancel: threading.Event | None = None,
    base_config: ComicboxSettings | None = None,
) -> Iterator[WriteResult]:
    """
    Write metadata to many files in parallel.

    Yields :class:`WriteResult` per file in *completion* order, not
    submission order. Caller may pass a ``cancel`` :class:`threading.Event`;
    if set, no new files are submitted (in-flight writes run to
    completion). ``on_event`` receives the shared :class:`comicbox.events`
    stream (``BatchStarted`` / ``FileParsed`` / ``FileError`` /
    ``BatchFinished``).
    """
    item_list = list(items)
    total = len(item_list)
    if on_event is not None:
        on_event(BatchStarted(total=total))

    parsed = 0
    errored = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for index, item in enumerate(item_list):
            if cancel is not None and cancel.is_set():
                break
            future = pool.submit(_write_one, item, base_config)
            futures[future] = (index, item)

        try:
            for future in as_completed(futures):
                index, item = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = WriteResult(path=item.path, error=exc)
                ok = _emit_write_event(result, index, total, on_event)
                if result.error is not None:
                    errored += 1
                    if stop_on_error and cancel is not None:
                        cancel.set()
                elif ok:
                    parsed += 1
                yield result
        finally:
            if on_event is not None:
                on_event(
                    BatchFinished(
                        total=total,
                        parsed=parsed,
                        short_circuited=0,
                        errored=errored,
                    )
                )


def _emit_write_event(
    result: WriteResult,
    index: int,
    total: int,
    on_event: EventHandler | None,
) -> bool:
    """Pick + emit the right event for a result. Return True if it was a parse."""
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
        on_event(
            FileShortCircuited(
                path=result.path,
                index=index,
                total=total,
                reason="filtered",
            )
        )
        return False
    on_event(FileParsed(path=result.path, index=index, total=total))
    return True


# --- internals --------------------------------------------------------------


def _write_one(
    item: BulkWriteItem, base_config: ComicboxSettings | None
) -> WriteResult:
    """Per-thread worker. Acquires the global write semaphore."""
    with _write_semaphore:
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
    new_write = WriteSettings(
        formats=formats,
        mode=mode,
        # Carry forward the rest of the base's WriteSettings so callers
        # who want stamp/etc. via base_config aren't clobbered.
        stamp=base.write.stamp,
        stamp_notes=base.write.stamp_notes,
        delete_all_tags=base.write.delete_all_tags,
    )
    return replace(base, write=new_write)


# Default workers for bulk_write — exposed for tests that want to inspect.
DEFAULT_WORKERS: Callable[[], int] | None = None
