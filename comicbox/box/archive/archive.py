"""Get ZipInfo like attributes from all archive info types."""

from __future__ import annotations

from tarfile import TarFile
from typing import TYPE_CHECKING, Any, cast

from comicbox._pdf import PDF_ENABLED

if TYPE_CHECKING:
    from pdffile import PDFFile
    from py7zr import SevenZipFile
    from py7zr.io import BytesIOFactory
    from rarfile import RarFile
    from zipremove import ZipFile

    from comicbox.box.archive.archiveinfo import InfoType

    ArchiveType = ZipFile | SevenZipFile | RarFile | TarFile | PDFFile
else:
    from comicbox._pdf import PDFFile

    ArchiveType = Any  # avoid pulling in py7zr / rarfile at module-load time


# Dispatch by attribute presence rather than isinstance — keeps the heavy
# py7zr / rarfile imports off the hot read path for CBZ-only workers.
# `reset` is unique to py7zr.SevenZipFile among the archive types we accept.


class Archive:
    """Generic Archive ZipFile like methods."""

    @staticmethod
    def namelist(archive: ArchiveType) -> tuple[str, ...]:
        """Return namelist."""
        return tuple(
            archive.getnames() if isinstance(archive, TarFile) else archive.namelist()
        )

    @staticmethod
    def infolist(archive: ArchiveType) -> tuple[InfoType, ...]:
        """Return infolist."""
        if isinstance(archive, TarFile):
            infolist = archive.getmembers()
        elif hasattr(archive, "reset"):  # SevenZipFile
            infolist = cast("SevenZipFile", archive).list()
        else:
            infolist = cast("ZipFile | RarFile | PDFFile", archive).infolist()
        return tuple(infolist)

    @staticmethod
    def _read_tarfile(archive: TarFile, filename: str) -> bytes:
        file_obj = archive.extractfile(filename)
        return file_obj.read() if file_obj else b""

    @staticmethod
    def _read_7zipfile(
        archive: SevenZipFile, factory: BytesIOFactory | None, filename: str
    ) -> bytes:
        """Read a single file from 7zip."""
        if not factory:
            return b""
        archive.extract(targets=[filename], factory=factory)
        file_obj = factory.products.get(filename)
        data = file_obj.read() if file_obj else b""
        archive.reset()
        return data

    @classmethod
    def read(
        cls,
        archive: ArchiveType,
        filename: str,
        factory: None | BytesIOFactory,
        pdf_format: str = "",
        props: dict | None = None,
    ) -> bytes:
        """Read one file in the archive's data."""
        if PDF_ENABLED and isinstance(archive, PDFFile):
            return archive.read(filename, fmt=pdf_format, props=props)
        if isinstance(archive, TarFile):
            return cls._read_tarfile(archive, filename)
        if hasattr(archive, "reset"):  # SevenZipFile
            return cls._read_7zipfile(cast("SevenZipFile", archive), factory, filename)
        return cast("ZipFile | RarFile | PDFFile", archive).read(filename)
