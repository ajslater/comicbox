"""
Put an archive's tail back when a write to it in place fails.

A re-tag of a CBZ rewrites only its tail: every byte from the first one the
write can change to the end of the file, which holds the trailing tag files,
the central directory and the end record. ``TailRollback`` keeps the old tail
and length in memory while that happens. If the write raises anything, a
keyboard interrupt included, the tail is written back and the file cut to its
old length, so the comic is as it was. A process killed part way can leave
the tag files damaged; the pages are never touched.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType
    from typing import Self

#: A write whose tail is larger than this copies the archive instead.
TAIL_CAP = 16 * 1024 * 1024


def _restore(path: Path, offset: int, tail: bytes, length: int) -> None:
    """Write an old tail back and cut the archive to its old length."""
    with path.open("r+b") as archive:
        archive.seek(offset)
        archive.write(tail)
        archive.truncate(length)
        archive.flush()
        os.fsync(archive.fileno())


class TailRollback:
    """Keep an archive's tail in memory while it is rewritten in place."""

    def __init__(self, path: Path, offset: int) -> None:
        """Name the archive and the first byte the write can change."""
        self._path = path
        self._offset = offset
        self._length = 0
        self._tail = b""

    def __enter__(self) -> Self:
        """Keep the tail and the length before anything changes."""
        with self._path.open("rb") as archive:
            self._length = archive.seek(0, os.SEEK_END)
            archive.seek(self._offset)
            self._tail = archive.read(self._length - self._offset)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Put the tail back if the write raised; the error is raised as before."""
        if exc_type is None:
            return
        try:
            _restore(self._path, self._offset, self._tail, self._length)
        except OSError as restore_error:
            logger.error(
                f"{self._path}: could not undo a failed write ({restore_error}):"
                " it may be damaged."
            )
