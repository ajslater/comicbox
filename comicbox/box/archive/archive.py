"""Get ZipInfo like attributes from all archive info types."""

from tarfile import TarFile
from typing import TYPE_CHECKING

from py7zr import SevenZipFile
from py7zr.io import BytesIOFactory
from rarfile import RarFile
from zipremove import ZipFile

from comicbox._pdf import PDF_ENABLED
from comicbox.box.archive.archiveinfo import InfoType

if TYPE_CHECKING:
    from pdffile import PDFFile
else:
    from comicbox._pdf import PDFFile

ArchiveType = ZipFile | SevenZipFile | RarFile | TarFile | PDFFile


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
        match archive:
            case TarFile():
                infolist = archive.getmembers()
            case SevenZipFile():
                infolist = archive.list()
            case _:
                infolist = archive.infolist()
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
            return archive.read(filename, fmt=pdf_format, props=props)  # ty: ignore[unknown-argument]
        match archive:
            case TarFile():
                data = cls._read_tarfile(archive, filename)
            case SevenZipFile():
                data = cls._read_7zipfile(archive, factory, filename)
            case _:
                data = archive.read(filename)
        return data
