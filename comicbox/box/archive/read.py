"""Comic archive read methods."""

import shutil
from pathlib import Path
from tarfile import TarFile
from zipfile import ZipFile

from pdffile import PDFFile
from py7zr import SevenZipFile
from rarfile import BadRarFile, RarFile

from comicbox.box.archive.init import ComicboxArchiveInit, archive_close
from comicbox.exceptions import UnsupportedArchiveTypeError


class ComicboxArchiveRead(ComicboxArchiveInit):
    """Comic archive read methods."""

    _COMMENT_ARCHIVE_TYPES = (ZipFile, RarFile)

    def _ensure_read_archive(self):
        if not self._archive_cls or not self._path:
            reason = "Cannot read archive without a path."
            raise ValueError(reason)

    def _get_archive_namelist(self):
        """Get list of files in the archive."""
        self._ensure_read_archive()
        if self._namelist is None:
            archive = self._get_archive()
            if isinstance(archive, TarFile):
                namelist = archive.getnames()
            else:
                namelist = archive.namelist()
            # SORTED CASE INSENSITIVELY
            namelist = tuple(sorted(namelist, key=lambda x: x.lower()))
            self._namelist: tuple[str, ...] | None = namelist
        return self._namelist

    def _get_info_fn(self, info) -> str:
        return getattr(info, self._info_fn_attr)

    def _get_info_size(self, info) -> int | None:
        return getattr(info, self._info_size_attr) if self._info_size_attr else None

    @archive_close
    def namelist(self):
        """Get the archive file namelist."""
        return self._get_archive_namelist()

    def _get_archive_infolist(self):
        """Get info list of members from the archive."""
        self._ensure_read_archive()
        if not self._infolist:
            archive = self._get_archive()
            if isinstance(archive, TarFile):
                infolist = archive.getmembers()
            elif isinstance(archive, SevenZipFile):
                infolist = archive.list()
            else:
                infolist = archive.infolist()

            # SORTED CASE INSENSITIVELY
            infolist = tuple(
                sorted(infolist, key=lambda i: self._get_info_fn(i).lower())
            )
            self._infolist: tuple | None = infolist
        return self._infolist

    @archive_close
    def infolist(self):
        """Get the archive file infolist."""
        return self._get_archive_infolist()

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

    @staticmethod
    def _read_tarfile(archive, filename: str) -> bytes:
        file_obj = archive.extractfile(filename)
        return file_obj.read() if file_obj else b""

    def _read_7zipfile(self, archive, filename: str) -> bytes:
        """Read a single file from 7zip."""
        if not self._7zfactory:
            return b""
        archive.extract(targets=[filename], factory=self._7zfactory)
        file_obj = self._7zfactory.products.get(filename)
        data = file_obj.read() if file_obj else b""
        archive.reset()
        return data

    def _archive_readfile(self, filename, *, to_pixmap=False) -> bytes:
        """Read an archive file to memory."""
        # Consider chunking files by 4096 bytes and streaming them.
        data = b""
        if Path(filename).is_dir():
            return data
        self._ensure_read_archive()
        archive = self._get_archive()
        if isinstance(archive, TarFile):
            data = self._read_tarfile(archive, filename)
        elif isinstance(archive, SevenZipFile):
            data = self._read_7zipfile(archive, filename)
        elif isinstance(archive, PDFFile) and to_pixmap:
            data = archive.read(filename, to_pixmap=True)
        else:
            try:
                data = archive.read(filename)  # pyright: ignore[reportCallIssue]
            except BadRarFile:
                self.check_unrar_executable()
                raise
        return data

    def _get_comment(self):
        """Get the comment from the archive."""
        archive = self._get_archive()
        comment = getattr(archive, "comment", b"")
        if isinstance(comment, str):
            comment = comment.encode(errors="replace")
        return comment
