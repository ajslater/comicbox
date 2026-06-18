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


class ComicboxError(Exception):
    """Base class for all operational errors comicbox raises."""


class UnsupportedArchiveTypeError(ComicboxError):
    """Unsupported Archive Type."""


class ArchiveError(ComicboxError):
    """An archive could not be opened or read."""


class ArchiveWriteError(ArchiveError):
    """An archive could not be written, repacked, or renamed."""


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
