"""Comic archive read methods."""
import shutil
from pathlib import Path
from tarfile import TarFile
from zipfile import ZipFile

from rarfile import BadRarFile, RarFile

from comicbox.box.archive import ComicboxArchiveMixin, archive_close
from comicbox.exceptions import UnsupportedArchiveTypeError


class ComicboxArchiveReadMixin(ComicboxArchiveMixin):
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
                namelist = archive.namelist()  # type: ignore
            # SORTED CASE INSENSITIVELY
            self._namelist = sorted(namelist, key=lambda x: x.lower())
        return self._namelist

    def _get_info_fn(self, info):
        return getattr(info, self._info_fn_attr)

    def _get_info_size(self, info):
        return getattr(info, self._info_size_attr)

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
            else:
                infolist = archive.infolist()  # type: ignore

            # SORTED CASE INSENSITIVELY
            self._infolist = sorted(
                infolist, key=lambda i: self._get_info_fn(i).lower()
            )
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

    def _archive_readfile(self, filename, to_pixmap=False) -> bytes:
        """Read an archive file to memory."""
        self._ensure_read_archive()
        archive = self._get_archive()
        if archive is None:
            reason = "problem getting archive."
            raise ValueError(reason)
        data = b""
        try:
            if isinstance(archive, TarFile):
                file_obj = archive.extractfile(filename)
                if file_obj:
                    data = file_obj.read()
            elif to_pixmap and self._archive_is_pdf:
                data = archive.read(filename, True)  # type: ignore
            else:
                data = archive.read(filename)
        except BadRarFile:
            self.check_unrar_executable()
            raise
        return data

    def _get_comment(self):
        """Get the comment from the archive."""
        comment = b""
        if self._archive_cls in self._COMMENT_ARCHIVE_TYPES:
            archive = self._get_archive()
            comment = archive.comment  # type: ignore
            if isinstance(comment, str):
                comment = comment.encode(errors="replace")
        return comment
