"""Get ZipInfo like attributes from all archive info types."""

from tarfile import TarFile
from zipfile import ZipFile

from py7zr import SevenZipFile
from py7zr.io import BytesIOFactory
from rarfile import RarFile

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.pdffile_stub import PDFFile

ArchiveType = ZipFile | SevenZipFile | RarFile | TarFile | PDFFile


class Archive:
    """Generic Archive ZipFile like methods."""

    @staticmethod
    def namelist(archive: ArchiveType):
        """Return namelist."""
        return (
            archive.getnames() if isinstance(archive, TarFile) else archive.namelist()
        )

    @staticmethod
    def infolist(archive: ArchiveType):
        """Return infolist."""
        if isinstance(archive, TarFile):
            infolist = archive.getmembers()
        elif isinstance(archive, SevenZipFile):
            infolist = archive.list()
        else:
            infolist = archive.infolist()
        return infolist

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
        *,
        to_pixmap: bool,
    ):
        """Read one file in the archive's data."""
        if isinstance(archive, TarFile):
            data = cls._read_tarfile(archive, filename)
        elif isinstance(archive, SevenZipFile):
            data = cls._read_7zipfile(archive, factory, filename)
        elif isinstance(archive, PDFFile) and to_pixmap:
            data = archive.read(filename, to_pixmap=True)
        else:
            data = archive.read(filename)
        return data
