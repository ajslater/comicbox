"""
Exceptions for comicbox.

Every operational error comicbox raises on a public path derives from
:class:`ComicboxError`, so library consumers can write ``except
ComicboxError`` without also swallowing unrelated programming errors
(``ValueError``, ``KeyError``, …) from their own code.

This module is a leaf: it must not import anything from comicbox, so any
module (including the format packages and the box mixins) can import it
without load-order concerns. The write/online modules re-export their
exceptions from here under their historical import paths.
"""

from pathlib import Path
from typing import Literal

from typing_extensions import override

DestinationKind = Literal["convert", "rename", "inflight"]


class ComicboxError(Exception):
    """Base class for all operational errors comicbox raises."""


class UnsupportedArchiveTypeError(ComicboxError):
    """Unsupported Archive Type."""


class ArchiveError(ComicboxError):
    """An archive could not be opened or read."""


class ArchiveWriteError(ArchiveError):
    """An archive could not be written, repacked, or renamed."""


class DestinationOccupiedError(ArchiveWriteError):
    """
    A write's destination path is held by another file or writer.

    ``kind`` says which collision: ``"convert"`` -- the CBZ this archive
    would repack to already exists (or another archive in the same batch
    claims it, in which case ``occupant`` names it); ``"rename"`` -- the
    predicted filename is taken; ``"inflight"`` -- another writer in this
    process holds the destination right now (transient; retry later).
    """

    def __init__(
        self,
        source: Path,
        destination: Path,
        kind: DestinationKind,
        occupant: Path | None = None,
    ) -> None:
        """Record the two paths, the collision kind, and any rival source."""
        self.source = source
        self.destination = destination
        self.kind = kind
        self.occupant = occupant
        super().__init__(self._message())

    def _message(self) -> str:
        """Render the frozen message text for this collision kind."""
        if self.kind == "inflight":
            return f"{self.destination} is already being written by another archive."
        if self.occupant is not None:
            return f"{self.destination} is also the destination of {self.occupant}."
        return f"{self.destination} already exists."

    @override
    def __reduce__(self) -> tuple:
        """
        Rebuild with the real signature when crossing a process boundary.

        Python unpickles an exception as ``cls(*self.args)``, which here
        is ``cls(message)`` -- a TypeError that would replace the real
        error with a bogus one on the far side. WriteResult.error is a
        public field, so keep it picklable.
        """
        return (type(self), (self.source, self.destination, self.kind, self.occupant))


class MetadataError(ComicboxError):
    """Metadata could not be loaded or routed through the source pipeline."""


class ExportError(ComicboxError):
    """A metadata file export failed its preconditions."""


class WriteValidationError(ComicboxError):
    """Raised when write_metadata inputs are inconsistent or invalid."""


class OnlineConfigurationError(ComicboxError):
    """Raised when OnlineSession inputs are inconsistent or incomplete."""


class OnlineLookupAbortedError(ComicboxError):
    """Raised when the selector callback returns ('abort', None)."""
