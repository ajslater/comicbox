"""Keep an archive's tail while it is rewritten in place, and put it back on failure."""

from __future__ import annotations

import os
import socket
from contextlib import suppress
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box.archive.journal.record import (
    BEFORE_SIZE,
    Header,
    closed,
    flush,
    journal_path,
    mark_owed,
    opened,
    read_range,
    restore,
    sha256,
)
from comicbox.box.archive.journal.replay import replay_journal
from comicbox.exceptions import ArchiveWriteError, DestinationOccupiedError

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType
    from typing import Self


class TailJournal:
    """
    Keep an archive's tail while it is rewritten in place, and put it back on failure.

    The tail is kept in memory and, where the directory can hold it, in a
    journal, complete and flushed before the archive is touched. A write
    that raises anything has the tail written back; one that succeeds is
    flushed, and its journal deleted.
    """

    def __init__(self, path: Path, offset: int) -> None:
        """Name the archive and the first byte the write can change."""
        self._path = path
        self._offset = offset
        self._journal = journal_path(path)
        self._length = 0
        self._tail = b""
        self._journaled = False

    def __enter__(self) -> Self:
        """Settle any journal there, then keep the tail before anything changes."""
        if replay_journal(self._path):
            reason = (
                f"{self._path} was restored from an interrupted write: write it again."
            )
            raise ArchiveWriteError(reason)
        with self._path.open("rb") as archive:
            self._length = archive.seek(0, os.SEEK_END)
            self._tail = read_range(archive, self._offset, self._length - self._offset)
            before_offset = max(0, self._offset - BEFORE_SIZE)
            before = read_range(archive, before_offset, self._offset - before_offset)
        header = Header(
            length=self._length,
            offset=self._offset,
            tail_sha256=sha256(self._tail),
            before_offset=before_offset,
            before_sha256=sha256(before),
            host=socket.gethostname(),
            pid=os.getpid(),
            rollback=0,
        )
        self._write_journal(header)
        return self

    def _write_journal(self, header: Header) -> None:
        """
        Write the journal, complete and flushed; go on without one where it cannot be.

        A directory that is read-only or full, or a name too long for it,
        leaves the in-memory rollback alone, which undoes a failed write but
        not a kill. The header goes to the file before the tail, so a journal
        a kill cut short still names its writer.
        """
        opened(self._journal)
        try:
            journal = self._journal.open("xb")
        except FileExistsError:
            closed(self._journal)
            raise DestinationOccupiedError(self._path, self._path, "writing") from None
        except OSError as exc:
            closed(self._journal)
            logger.debug(f"{self._path}: writing without a journal: {exc}")
            return
        try:
            with journal:
                journal.write(header.to_bytes())
                journal.flush()
                journal.write(self._tail)
                flush(journal)
        except OSError as exc:
            self._discard_journal()
            logger.debug(f"{self._path}: writing without a journal: {exc}")
            return
        except BaseException:
            self._discard_journal()
            raise
        self._journaled = True

    def _discard_journal(self) -> None:
        with suppress(OSError):
            self._journal.unlink()
        closed(self._journal)

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
        """
        Flush the written archive, then delete the journal.

        The handle flushed is opened for writing, as Windows requires. A
        journal that cannot be deleted leaves the write standing, with a
        warning: the next open finds the archive whole and removes it.
        """
        with self._path.open("r+b") as archive:
            os.fsync(archive.fileno())
        closed(self._journal)
        if not self._journaled:
            return
        try:
            self._journal.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                f"{self._path}: written, but cannot remove {self._journal.name}: {exc}"
            )

    def _rollback(self) -> None:
        """
        Put the old tail back; keep the journal if that fails.

        Either way this process stops counting the journal as its own, so a
        journal a failed rollback leaves is stale to it and settled on its
        next open.
        """
        closed(self._journal)
        try:
            restore(self._path, self._offset, self._tail, self._length)
        except OSError as exc:
            # The archive can verify now, half written: the journal must say
            # it is owed a rollback, or the next open would keep that.
            kept = (
                f"{self._journal.name} will undo it the next time comicbox opens it"
                if self._journaled and mark_owed(self._journal)
                else "it may be damaged"
            )
            logger.error(
                f"{self._path}: could not undo a failed write ({exc}): {kept}."
            )
            return
        if self._journaled:
            with suppress(OSError):
                self._journal.unlink()
