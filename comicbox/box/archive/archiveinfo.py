"""Get ZipInfo like attributes from all archive info types."""

from __future__ import annotations

from datetime import datetime, timezone
from tarfile import TarInfo
from typing import TYPE_CHECKING, Any, cast
from zipfile import ZipInfo

if TYPE_CHECKING:
    from py7zr import FileInfo as SevenZipInfo
    from rarfile import RarInfo

    InfoType = ZipInfo | SevenZipInfo | RarInfo | TarInfo
else:
    InfoType = Any  # avoid pulling in py7zr / rarfile at module-load time


# Dispatch by attribute presence rather than isinstance, so we don't trigger
# the py7zr / rarfile imports on hot read paths that only see CBZ / CBT files.


class ArchiveInfo:
    """Get ZipInfo like attributes from all archive info types."""

    @staticmethod
    def mtime(info: InfoType) -> datetime | None:
        """Return mtime as a datetime."""
        dttm = None
        if isinstance(info, ZipInfo):
            if date_time := info.date_time:
                dttm = datetime(*date_time)  # noqa: DTZ001
        elif isinstance(info, TarInfo):
            dttm = datetime.fromtimestamp(info.mtime, tz=timezone.utc)
        elif hasattr(info, "creationtime"):  # SevenZipInfo
            dttm = cast("SevenZipInfo", info).creationtime
        elif mtime := cast("RarInfo", info).mtime:
            dttm = mtime
        if dttm:
            if not dttm.tzinfo:
                dttm = dttm.replace(tzinfo=timezone.utc)
            if type(dttm) is not datetime:
                # rarfile returns an nsdatetime (a datetime subclass) that has
                # no __reduce__, so pickling it across a ProcessPoolExecutor
                # boundary breaks on unpickle and poisons the worker pool.
                # Coerce any datetime subclass to a plain, picklable datetime.
                dttm = datetime(
                    dttm.year,
                    dttm.month,
                    dttm.day,
                    dttm.hour,
                    dttm.minute,
                    dttm.second,
                    dttm.microsecond,
                    dttm.tzinfo,
                    fold=dttm.fold,
                )
        return dttm

    @staticmethod
    def is_dir(info: InfoType) -> bool:
        """Is a directory."""
        if isinstance(info, TarInfo):
            return info.isdir()
        if hasattr(info, "is_directory"):  # SevenZipInfo
            return bool(cast("SevenZipInfo", info).is_directory)
        # ZipInfo or RarInfo
        return cast("ZipInfo | RarInfo", info).is_dir()

    @staticmethod
    def filename(info: InfoType) -> str:
        """Return archive filename."""
        filename = info.name if isinstance(info, TarInfo) else info.filename
        return filename or ""
