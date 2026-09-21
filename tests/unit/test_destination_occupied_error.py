"""
The typed destination-collision error.

Its message texts are frozen: they are what every pre-5.2.0 caller
matched on, and the type is the replacement for that matching. Its
``__init__`` signature is not ``(message,)``, so it also has to survive a
process boundary -- ``WriteResult.error`` is a public field and Python
rebuilds an unpickled exception as ``cls(*self.args)``.
"""

from __future__ import annotations

import pickle
from pathlib import Path

from comicbox.exceptions import (
    ArchiveWriteError,
    ComicboxError,
    DestinationOccupiedError,
)
from comicbox.write import DestinationOccupiedError as WriteDestinationOccupiedError

_SOURCE = Path("/comics/Captain Science #001.cbr")
_DESTINATION = Path("/comics/Captain Science #001.cbz")
_OCCUPANT = Path("/comics/Captain Science #001.cbt")


def test_convert_message_is_unchanged() -> None:
    """The on-disk collision still says what it always said."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "convert")

    assert "already exists" in str(exc)
    assert str(exc) == f"{_DESTINATION} already exists."


def test_rename_message_is_unchanged() -> None:
    """A rename collision renders the same text as a conversion's."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "rename")

    assert "already exists" in str(exc)


def test_inflight_message_is_unchanged() -> None:
    """The in-flight claim refusal still says what it always said."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "inflight")

    assert "already being written" in str(exc)
    assert str(exc) == f"{_DESTINATION} is already being written by another archive."


def test_an_occupant_is_named_in_the_message() -> None:
    """A batch collision names the archive that claimed the name first."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "convert", _OCCUPANT)

    assert str(exc) == f"{_DESTINATION} is also the destination of {_OCCUPANT}."


def test_it_is_an_archive_write_error() -> None:
    """``except ArchiveWriteError`` and ``except ComicboxError`` still catch it."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "convert")

    assert isinstance(exc, ArchiveWriteError)
    assert isinstance(exc, ComicboxError)


def test_it_survives_a_process_boundary() -> None:
    """
    Unpickling rebuilds the real error, not a TypeError.

    Python rebuilds an exception as ``cls(*self.args)``; without
    ``__reduce__`` that is ``cls(message)`` here, and the far side of any
    process boundary sees a TypeError in place of the collision.
    """
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "convert", _OCCUPANT)

    restored = pickle.loads(pickle.dumps(exc))  # noqa: S301

    assert isinstance(restored, DestinationOccupiedError)
    assert restored.source == _SOURCE
    assert restored.destination == _DESTINATION
    assert restored.kind == "convert"
    assert restored.occupant == _OCCUPANT
    assert str(restored) == str(exc)


def test_it_survives_a_process_boundary_without_an_occupant() -> None:
    """The three-argument form round trips too."""
    exc = DestinationOccupiedError(_SOURCE, _DESTINATION, "inflight")

    restored = pickle.loads(pickle.dumps(exc))  # noqa: S301

    assert restored.occupant is None
    assert restored.kind == "inflight"
    assert str(restored) == str(exc)


def test_it_is_importable_from_the_write_api() -> None:
    """Both public import paths name one class."""
    assert WriteDestinationOccupiedError is DestinationOccupiedError
