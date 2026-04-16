"""Comicbox methods on the archive itself."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import comicbox.box.archive.read

import re

from loguru import logger
from typing_extensions import Self

from comicbox.box.init import ComicboxInit
from comicbox.box.types import ArchiveType


class ComicboxArchiveInit(ComicboxInit):
    """Methods on the archive itself."""

    IMAGE_EXT_RE = re.compile(r"\.(jxl|jpe?g|webp|png|gif)$", re.IGNORECASE)

    def __enter__(self: "comicbox.box.archive.read.ComicboxArchiveInit") -> Self:
        """Context enter."""
        return self

    def __exit__(self: "comicbox.box.archive.read.ComicboxArchiveInit", *_exc: object) -> bool | None:
        """Context close."""
        self.close()

    def close(self: "comicbox.box.archive.read.ComicboxArchiveInit") -> None:
        """Close the open archive."""
        try:
            if self._archive and hasattr(self._archive, "close"):
                self._archive.close()
        except Exception as exc:
            logger.warning(f"closing archive {self._path}: {exc}")
        finally:
            self._archive = None

    def _get_archive(self: "comicbox.box.archive.read.ComicboxArchiveInit") -> ArchiveType:
        """Set archive instance open for reading."""
        if not self._archive and self._archive_cls:
            self._archive = self._archive_cls(self._path)
        if not self._archive:
            reason = f"Unable to make archive from class {self._archive_cls}"
            raise ValueError(reason)
        return self._archive
