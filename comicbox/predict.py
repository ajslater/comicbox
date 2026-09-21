"""
Public prediction API: where a write would land, before anything is written.

``write_metadata(dry_run=True)`` previews the *payload* and deliberately
keeps reporting ``final_path=None``; it says nothing about the
destination. This module is the destination preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from comicbox.box import Comicbox

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings


@dataclass(frozen=True, slots=True)
class WriteDestination:
    """Where a write of one archive would land."""

    # The path as submitted.
    path: Path
    # Where the write lands; equal to ``path`` for an in-place write.
    destination: Path
    # True when the write would repack to a new file rather than rewrite
    # the archive in place.
    converts: bool
    # True when ``converts`` and something already occupies ``destination``.
    occupied: bool


def predict_write_destination(
    path: Path | str, *, base_config: ComicboxSettings | None = None
) -> WriteDestination:
    """
    Report where a write to ``path`` would land, and whether that path is taken.

    The archive's sniffed type decides, never its suffix: a RAR named
    ``X.cbz`` reports ``converts=False`` because its repack lands on its
    own name, and a zip named ``X.cbr`` is rewritten in place.

    Opens nothing. Construction sniffs the archive type from the file's
    leading bytes and stops there -- no member listing, no decompression,
    no schema load -- so this is cheap enough to run over a whole batch
    before any of it is written.

    Raises whatever ``Comicbox`` construction raises and leaves the
    handling to the caller: ``FileNotFoundError`` and
    ``IsADirectoryError`` for a path that is not a readable file, and
    :class:`comicbox.exceptions.UnsupportedArchiveTypeError` for bytes
    that are no archive comicbox knows.

    Pass a prebuilt ``base_config`` when predicting a batch. ``None``
    rebuilds the config from files and environment on every call, which
    is fine for one file and wasteful for many.
    """
    box = Comicbox(path, config=base_config)
    # get_write_destination() raises without a path, so get_path() is set
    # by the time the fallback would matter.
    destination = box.get_write_destination()
    submitted = box.get_path() or Path(path)
    converts = destination != submitted
    return WriteDestination(
        path=submitted,
        destination=destination,
        converts=converts,
        occupied=converts and destination.is_file(),
    )
