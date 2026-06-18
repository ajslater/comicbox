"""The ComicboxError hierarchy contract for library consumers."""

from __future__ import annotations

from pathlib import Path

import pytest

from comicbox import exceptions
from comicbox.box import Comicbox
from comicbox.exceptions import ComicboxError
from comicbox.write import WriteValidationError, write_metadata

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


def test_historical_import_paths_still_work() -> None:
    """The pre-hierarchy import locations keep resolving."""
    from comicbox.box.online_lookup import OnlineLookupAbortedError
    from comicbox.online_session import OnlineConfigurationError

    assert OnlineLookupAbortedError is exceptions.OnlineLookupAbortedError
    assert OnlineConfigurationError is exceptions.OnlineConfigurationError
    assert WriteValidationError is exceptions.WriteValidationError


def test_write_validation_catchable_as_comicbox_error() -> None:
    with pytest.raises(ComicboxError):
        write_metadata(Path("irrelevant.cbz"), patch={}, formats=["comic_info"])


def test_pathless_read_raises_archive_error() -> None:
    """Operational misuse raises a ComicboxError subclass, not ValueError."""
    cb = Comicbox()
    with pytest.raises(exceptions.ArchiveError):
        cb.namelist()
