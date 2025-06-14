"""Get ZipInfo like attributes from all archive info types."""

from datetime import datetime, timezone
from tarfile import TarInfo
from zipfile import ZipInfo

from py7zr import FileInfo as SevenZipInfo
from rarfile import RarInfo

InfoType = ZipInfo | SevenZipInfo | RarInfo | TarInfo


class ArchiveInfo:
    """Get ZipInfo like attributes from all archive info types."""

    @staticmethod
    def datetime(info: InfoType) -> datetime | None:
        """Return mtime as a datetime."""
        dttm = None
        if isinstance(info, ZipInfo):
            if date_time := info.date_time:
                dttm = datetime(*date_time, tzinfo=timezone.utc)
        elif isinstance(info, TarInfo):
            dttm = datetime.fromtimestamp(info.mtime, tz=timezone.utc)
        elif isinstance(info, SevenZipInfo):
            dttm = info.creationtime
        elif mtime := info.mtime:  # RarInfo
            dttm = mtime
        return dttm

    @staticmethod
    def is_dir(info: InfoType) -> bool:
        """Is a directory."""
        if isinstance(info, ZipInfo | RarInfo):
            is_dir = info.is_dir()
        elif isinstance(info, TarInfo):
            is_dir = info.isdir()
        else:  # SevenZipInfo):
            is_dir = bool(info.is_directory)
        return is_dir

    @staticmethod
    def filename(info: InfoType) -> str:
        """Return archive filename."""
        filename = info.name if isinstance(info, TarInfo) else info.filename
        return filename or ""
