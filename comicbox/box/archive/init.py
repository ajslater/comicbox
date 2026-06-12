"""Comicbox methods on the archive itself."""

import re

from loguru import logger
from typing_extensions import Self

from comicbox.box.init import ComicboxInit
from comicbox.box.types import ArchiveType
from comicbox.exceptions import ArchiveError


class ComicboxArchiveInit(ComicboxInit):
    """Methods on the archive itself."""

    IMAGE_EXT_RE = re.compile(r"\.(jxl|jpe?g|webp|png|gif)$", re.IGNORECASE)

    def __enter__(self) -> Self:
        """Context enter."""
        return self

    def __exit__(self, *_exc: object) -> bool | None:
        """Context close."""
        self.close()

    def close(self) -> None:
        """Close the open archive and release cached archive state."""
        try:
            if self._archive and hasattr(self._archive, "close"):
                self._archive.close()
        except Exception as exc:
            logger.warning(f"closing archive {self._path}: {exc}")
        finally:
            self._archive = None
            # Release the 7z page-buffer factory — Py7zBytesIO objects
            # accumulate one entry per page ever read and are otherwise
            # only freed when the Comicbox instance is GC'd. Long-lived
            # callers (Codex's ArchiveCache) need explicit release.
            self._7zfactory = None
            # Drop cached archive directory listings as well; they can
            # be many KB on archives with hundreds of pages.
            self._namelist = None
            self._infolist = None

    def _get_archive(self) -> ArchiveType:
        """Set archive instance open for reading."""
        if not self._archive and self._archive_cls:
            self._archive = self._archive_cls(self._path)
        if not self._archive:
            reason = f"Unable to make archive from class {self._archive_cls}"
            raise ArchiveError(reason)
        return self._archive
