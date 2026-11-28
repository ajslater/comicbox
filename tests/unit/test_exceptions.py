"""The ComicboxError hierarchy contract for library consumers."""

from __future__ import annotations

from pathlib import Path

import pytest

from comicbox import exceptions
from comicbox.box import Comicbox
from comicbox.exceptions import ComicboxError
from comicbox.write import write_metadata

PUBLIC_EXCEPTIONS = (
    exceptions.UnsupportedArchiveTypeError,
    exceptions.ArchiveError,
    exceptions.ArchiveWriteError,
    exceptions.MetadataError,
    exceptions.ExportError,
    exceptions.WriteValidationError,
    exceptions.OnlineConfigurationError,
    exceptions.OnlineLookupAbortedError,
)


def test_all_public_exceptions_share_the_base() -> None:
    """Except ComicboxError catches every operational comicbox error."""
    for exc_class in PUBLIC_EXCEPTIONS:
        assert issubclass(exc_class, ComicboxError)


def test_the_api_modules_export_the_errors_they_raise() -> None:
    """The write and online-session APIs hand out the errors they raise."""
    from comicbox import online_session, write

    assert write.WriteValidationError is exceptions.WriteValidationError
    assert write.DestinationOccupiedError is exceptions.DestinationOccupiedError
    assert online_session.OnlineConfigurationError is (
        exceptions.OnlineConfigurationError
    )


def test_write_validation_catchable_as_comicbox_error() -> None:
    with pytest.raises(ComicboxError):
        write_metadata(Path("irrelevant.cbz"), patch={}, formats=["comic_info"])


def test_pathless_read_raises_archive_error() -> None:
    """Operational misuse raises a ComicboxError subclass, not ValueError."""
    cb = Comicbox()
    with pytest.raises(exceptions.ArchiveError):
        cb.namelist()
