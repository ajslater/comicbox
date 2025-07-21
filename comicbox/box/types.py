"""Comicbox Types."""

from tarfile import TarFile

from py7zr import SevenZipFile
from rarfile import RarFile
from zipremove import ZipFile

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.pdffile_stub import PDFFile


ArchiveType = ZipFile | RarFile | TarFile | SevenZipFile | PDFFile
