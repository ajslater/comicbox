"""Comicbox Archive."""

from comicbox.box.archive.init import archive_close
from comicbox.box.archive.pages import ComicboxArchivePages

__all__ = ("ComicboxArchive", "archive_close")


class ComicboxArchive(ComicboxArchivePages):
    """Comicbox Archive."""
