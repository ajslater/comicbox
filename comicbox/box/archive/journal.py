"""
Undo an in-place tag write that did not finish.

A re-tag of a CBZ rewrites only its tail: every byte from the first one the
write can change to the end of the file, which holds the trailing tag files,
the central directory and the end record. ``TailJournal`` keeps the old tail
while that happens. If the write raises anything, a keyboard interrupt
included, the tail is written back and the file cut to its old length.

A copy of the tail also goes to a journal beside the archive, flushed before
the archive is touched and deleted once the write is flushed. A write killed
part way leaves the journal, and ``replay_journal``, run whenever comicbox
opens a comic, puts the tail back. The journal is
``.<archive name>.comicbox-journal.tmp``: a dot name ending in ``.tmp``, which
a library watcher skips, and never a comic suffix.

A journal holds a marker and version line, a JSON header (the old length, the
tail's offset and checksum, a checksum of the bytes just before the tail, to
show the pages are the ones it was taken from, and the writer's host and
process id), then the tail.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING, Any, BinaryIO

from loguru import logger

from comicbox.exceptions import (
    ArchiveError,
    ArchiveWriteError,
    DestinationOccupiedError,
)

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType
    from typing import Self

JOURNAL_SUFFIX = ".comicbox-journal.tmp"
#: A write whose tail is larger than this copies the archive instead.
TAIL_CAP = 16 * 1024 * 1024
_MAGIC = b"comicbox-journal 1\n"
# The bytes before the tail whose checksum the journal keeps.
_BEFORE_SIZE = 64 * 1024
_MAX_HEADER_SIZE = 4096


def journal_path(path: Path) -> Path:
    """
    Name an archive's journal: beside the file itself.

    Through a link, that is beside the link's target, so every name a comic
    is opened by finds the one journal. A linked directory needs no
    resolving, which is most of what a check costs: the file's name in it
    is the file's own.
    """
    real = path.resolve() if path.is_symlink() else path
    return real.with_name(f".{real.name}{JOURNAL_SUFFIX}")


@dataclass(frozen=True, slots=True)
class _Header:
    length: int
    offset: int
    tail_sha256: str
    before_offset: int
    before_sha256: str
    host: str
    pid: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_range(archive: BinaryIO, start: int, size: int) -> bytes:
    archive.seek(start)
    return archive.read(size)


def _flush(stream: BinaryIO) -> None:
    stream.flush()
    os.fsync(stream.fileno())


def _restore(path: Path, offset: int, tail: bytes, length: int) -> None:
    """Write the old tail back and cut the archive to its old length."""
    with path.open("r+b") as archive:
        archive.seek(offset)
        archive.write(tail)
        archive.truncate(length)
        _flush(archive)


def _windows_pid_alive(pid: int) -> bool:  # pragma: no cover
    import ctypes

    # os.kill(pid, 0) would end the process on Windows.
    kernel32 = ctypes.windll.kernel32  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
    query_limited_information, still_active, access_denied = 0x1000, 259, 5
    handle = kernel32.OpenProcess(query_limited_information, False, pid)  # noqa: FBT003
    if not handle:
        return kernel32.GetLastError() == access_denied
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _writer_alive(header: _Header) -> bool:
    return header.host == socket.gethostname() and _pid_alive(header.pid)


def _parse(data: bytes) -> tuple[_Header, bytes] | None:
    """Read a journal's header and tail; None for anything that is not one."""
    if not data.startswith(_MAGIC):
        return None
    end = data.find(b"\n", len(_MAGIC), len(_MAGIC) + _MAX_HEADER_SIZE)
    if end < 0:
        return None
    try:
        raw: Any = json.loads(data[len(_MAGIC) : end])
        header = _Header(**{field.name: raw[field.name] for field in fields(_Header)})
    except (ValueError, TypeError, KeyError):
        return None
    return header, data[end + 1 :]


def _fits(path: Path, header: _Header, tail: bytes) -> bool:
    """Tell whether a journal was taken from this archive, and is whole."""
    if not (
        0 <= header.before_offset <= header.offset <= header.length
        and header.length - header.offset == len(tail) <= TAIL_CAP
        and _sha256(tail) == header.tail_sha256
    ):
        return False
    try:
        with path.open("rb") as archive:
            size = header.offset - header.before_offset
            before = _read_range(archive, header.before_offset, size)
    except OSError:
        return False
    return len(before) == size and _sha256(before) == header.before_sha256


def replay_journal(path: Path) -> bool:
    """
    Undo a write a kill left half done, before the comic is read; whether it did.

    A journal whose writer is alive on this host means a write is in flight,
    and the comic is refused. One that does not fit the archive is left
    alone, with a warning, and the comic is opened as it is.
    """
    journal = journal_path(path)
    try:
        data = journal.read_bytes()
    except FileNotFoundError:
        return False
    except OSError as exc:
        reason = f"{path} has a write journal that cannot be read: {exc}"
        raise ArchiveError(reason) from exc
    if (parsed := _parse(data)) is None:
        logger.warning(f"{path}: {journal.name} is not a comicbox journal; left alone.")
        return False
    header, tail = parsed
    if _writer_alive(header):
        raise DestinationOccupiedError(path, path, "writing")
    if not _fits(path, header, tail):
        logger.warning(
            f"{path}: {journal.name} does not fit the comic; left alone,"
            " and the comic read as it is."
        )
        return False
    try:
        _restore(path, header.offset, tail, header.length)
        journal.unlink()
    except OSError as exc:
        reason = f"{path}: an interrupted write could not be undone: {exc}"
        raise ArchiveError(reason) from exc
    logger.warning(f"{path}: undid a write that was interrupted.")
    return True


class TailJournal:
    """Keep an archive's tail while it is rewritten in place, and put it back on failure."""

    def __init__(self, path: Path, offset: int) -> None:
        """Name the archive and the first byte the write can change."""
        self._path = path
        self._offset = offset
        self._journal = journal_path(path)
        self._length = 0
        self._tail = b""
        self._journaled = False

    def __enter__(self) -> Self:
        """Keep the tail, in memory and in the journal, before anything changes."""
        with self._path.open("rb") as archive:
            self._length = archive.seek(0, os.SEEK_END)
            self._tail = _read_range(archive, self._offset, self._length - self._offset)
            before_offset = max(0, self._offset - _BEFORE_SIZE)
            before = _read_range(archive, before_offset, self._offset - before_offset)
        header = _Header(
            length=self._length,
            offset=self._offset,
            tail_sha256=_sha256(self._tail),
            before_offset=before_offset,
            before_sha256=_sha256(before),
            host=socket.gethostname(),
            pid=os.getpid(),
        )
        self._write_journal(header)
        return self

    def _write_journal(self, header: _Header) -> None:
        """
        Write and flush the journal; go on without one where it cannot be.

        A directory that is read-only or full leaves the in-memory rollback
        alone, which undoes a failed write but not a kill.
        """
        try:
            journal = self._journal.open("xb")
        except FileExistsError:
            self._found_journal()
            return
        except OSError as exc:
            logger.debug(f"{self._path}: writing without a journal: {exc}")
            return
        try:
            with journal:
                journal.write(_MAGIC)
                journal.write(json.dumps(asdict(header)).encode() + b"\n")
                journal.write(self._tail)
                _flush(journal)
        except OSError as exc:
            with suppress(OSError):
                self._journal.unlink()
            logger.debug(f"{self._path}: writing without a journal: {exc}")
            return
        except BaseException:
            with suppress(OSError):
                self._journal.unlink()
            raise
        self._journaled = True

    def _found_journal(self) -> None:
        """
        Meet a journal that appeared after the comic was opened.

        A live writer's is refused, and a dead writer's replayed, which
        changes the archive under this write, so it is refused too. One that
        does not fit is left alone, and this write goes on without its own.
        """
        if replay_journal(self._path):
            reason = (
                f"{self._path} was restored from an interrupted write: write it again."
            )
            raise ArchiveWriteError(reason)
        logger.debug(
            f"{self._path}: writing without a journal: {self._journal.name} is in the way"
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Flush the archive and delete the journal, or put the tail back."""
        if exc_type is None:
            try:
                self._finish()
            except BaseException:
                self._rollback()
                raise
            return
        self._rollback()

    def _finish(self) -> None:
        with self._path.open("rb") as archive:
            os.fsync(archive.fileno())
        if self._journaled:
            self._journal.unlink()

    def _rollback(self) -> None:
        """Put the old tail back; keep the journal if that fails."""
        try:
            _restore(self._path, self._offset, self._tail, self._length)
        except OSError as exc:
            kept = (
                f"{self._journal.name} will undo it the next time comicbox opens it"
                if self._journaled
                else "it may be damaged"
            )
            logger.error(
                f"{self._path}: could not undo a failed write ({exc}): {kept}."
            )
            return
        if self._journaled:
            with suppress(OSError):
                self._journal.unlink()
