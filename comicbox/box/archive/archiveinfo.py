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
        match info:
            case ZipInfo():
                if date_time := info.date_time:
                    dttm = datetime(*date_time)  # noqa: DTZ001
            case TarInfo():
                dttm = datetime.fromtimestamp(info.mtime, tz=timezone.utc)
            case SevenZipInfo():
                dttm = info.creationtime
            case _:  # RarInfo
                if mtime := info.mtime:
                    dttm = mtime
        if dttm and not dttm.tzinfo:
            dttm = dttm.replace(tzinfo=timezone.utc)
        return dttm

    @staticmethod
    def is_dir(info: InfoType) -> bool:
        """Is a directory."""
        match info:
            case ZipInfo() | RarInfo():
                is_dir = info.is_dir()
            case TarInfo():
                is_dir = info.isdir()
            case _:  # SevenZipInfo
                is_dir = bool(info.is_directory)
        return is_dir

    @staticmethod
    def filename(info: InfoType) -> str:
        """Return archive filename."""
        filename = info.name if isinstance(info, TarInfo) else info.filename
        return filename or ""
