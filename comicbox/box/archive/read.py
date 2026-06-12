"""Comic archive read methods."""

from __future__ import annotations

import shutil
from pathlib import Path
from sys import maxsize
from typing import TYPE_CHECKING

from comicbox.box.archive.archive import Archive
from comicbox.box.archive.init import ComicboxArchiveInit
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import ArchiveError, UnsupportedArchiveTypeError

if TYPE_CHECKING:
    from py7zr.io import BytesIOFactory

    from comicbox.box.archive.archiveinfo import InfoType


class ComicboxArchiveRead(ComicboxArchiveInit):
    """Comic archive read methods."""

    def _ensure_read_archive(self) -> None:
        if not self._archive_cls or not self._path:
            reason = "Cannot read archive without a path."
            raise ArchiveError(reason)

    def namelist(self) -> tuple[str, ...]:
        """Get list of files in the archive."""
        self._ensure_read_archive()
        if self._namelist is None:
            if self._infolist:
                # Derive from cached infolist - both are sorted by the same
                # lowercased-filename key, so re-sort is unnecessary.
                self._namelist: tuple[str, ...] | None = tuple(
                    self._get_info_fn(i) for i in self._infolist
                )
            else:
                archive = self._get_archive()
                namelist = Archive.namelist(archive)
                # SORTED CASE INSENSITIVELY
                self._namelist = tuple(sorted(namelist, key=lambda x: x.lower()))
        return self._namelist

    def _get_info_fn(self, info: InfoType) -> str:
        return getattr(info, self._info_fn_attr)

    def _get_info_size(self, info: InfoType) -> int | None:
        return getattr(info, self._info_size_attr) if self._info_size_attr else None

    def infolist(self) -> tuple[InfoType, ...]:
        """Get info list of members from the archive."""
        self._ensure_read_archive()
        if not self._infolist:
            archive = self._get_archive()
            infolist = Archive.infolist(archive)
            # SORTED CASE INSENSITIVELY
            infolist = tuple(
                sorted(infolist, key=lambda i: self._get_info_fn(i).lower())
            )
            self._infolist = infolist
        return self._infolist

    @classmethod
    def check_unrar_executable(cls) -> bool:
        """Check for the unrar executable."""
        unrar_path = shutil.which("unrar")
        if not unrar_path:
            reason = "'unrar' not on path"
            raise UnsupportedArchiveTypeError(reason)
        mode = Path(unrar_path).stat().st_mode
        if not bool(mode & cls._MODE_EXECUTABLE):
            reason = f"'{unrar_path}' not executable"
            raise UnsupportedArchiveTypeError(reason)
        return True

    @classmethod
    def is_unrar_supported(cls) -> bool:
        """Return if rar file contents can be read."""
        try:
            return cls.check_unrar_executable()
        except UnsupportedArchiveTypeError:
            return False

    def _get_7zfactory(self) -> BytesIOFactory | None:
        # Use the file-type enum rather than `self._archive_cls == SevenZipFile`
        # so the py7zr import only fires when we actually have a CB7.
        if not self._7zfactory and self._file_type == FileTypeEnum.CB7:
            from py7zr.io import BytesIOFactory

            self._7zfactory: BytesIOFactory | None = BytesIOFactory(maxsize)
        return self._7zfactory

    def _get_pdf_format(self, pdf_format: str = "", default: str = "") -> str:
        return pdf_format or (self._config.convert.pdf_pages or default)

    def _archive_readfile(
        self, filename: str, pdf_format: str = "", props: dict | None = None
    ) -> bytes:
        """Read an archive file to memory."""
        # Consider chunking files by 4096 bytes and streaming them.
        data = b""
        if Path(filename).is_dir():
            return data
        self._ensure_read_archive()
        archive = self._get_archive()
        factory = self._get_7zfactory()
        pdf_format = self._get_pdf_format(pdf_format)
        try:
            data = Archive.read(
                archive, filename, factory, pdf_format=pdf_format, props=props
            )
        except Exception as exc:
            # BadRarFile only originates from CBR reads; the lazy import
            # keeps rarfile off the CBZ-only critical path.
            if self._file_type == FileTypeEnum.CBR:
                from rarfile import BadRarFile

                if isinstance(exc, BadRarFile):
                    self.check_unrar_executable()
            raise
        return data

    def _get_comment(self) -> bytes:
        """Get the comment from the archive."""
        archive = self._get_archive()
        comment = getattr(archive, "comment", b"")
        if isinstance(comment, str):
            comment = comment.encode(errors="replace")
        return comment
