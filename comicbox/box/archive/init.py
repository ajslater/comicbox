"""Comicbox methods on the archive itself."""

import re
from typing import Self

from loguru import logger

from comicbox._rar import rar_unsupported_reason
from comicbox.box.init import ComicboxInit
from comicbox.box.types import ArchiveType
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import ArchiveError, UnsupportedArchiveTypeError

#: Page image extensions, without the dot. `comicbox doctor` checks each
#: against the installed Pillow's codecs.
IMAGE_EXTS = ("jxl", "jpg", "jpeg", "webp", "png", "gif")


class ComicboxArchiveInit(ComicboxInit):
    """Methods on the archive itself."""

    IMAGE_EXT_RE = re.compile(rf"\.({'|'.join(IMAGE_EXTS)})$", re.IGNORECASE)

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
            self._dirnames = None

    def _raise_if_rar_tool_failure(self, exc: Exception) -> None:
        """
        Replace a RAR tool failure with the missing-tool error behind it.

        rarfile reports an unusable extraction tool as ``RarCannotExec``
        (nothing to run) or ``BadRarFile`` (the tool ran and returned short
        output). The latter is also how it reports a corrupt archive, so
        only the host probe can tell the two apart.
        """
        if self._file_type != FileTypeEnum.CBR:
            return
        # Lazy: keeps rarfile off the CBZ-only critical path.
        from rarfile import BadRarFile, RarCannotExec

        if isinstance(exc, BadRarFile | RarCannotExec) and (
            reason := rar_unsupported_reason()
        ):
            raise UnsupportedArchiveTypeError(reason) from exc

    def _get_archive(self) -> ArchiveType:
        """Set archive instance open for reading."""
        if not self._archive and self._archive_cls:
            try:
                self._archive = self._archive_cls(self._path)
            except Exception as exc:
                # Opening needs the tool too: rarfile decompresses a RAR3
                # archive comment while constructing the RarFile.
                self._raise_if_rar_tool_failure(exc)
                raise
        if not self._archive:
            reason = f"Unable to make archive from class {self._archive_cls}"
            raise ArchiveError(reason)
        return self._archive
