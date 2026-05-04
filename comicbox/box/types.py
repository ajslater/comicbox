"""Comicbox Types."""

from tarfile import TarFile
from typing import TYPE_CHECKING

from py7zr import SevenZipFile
from rarfile import RarFile
from zipremove import ZipFile

if TYPE_CHECKING:
    from pdffile import PDFFile
else:
    from comicbox._pdf import PDFFile


ArchiveType = ZipFile | RarFile | TarFile | SevenZipFile | PDFFile
