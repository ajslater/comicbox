"""Comicbox Types."""

from tarfile import TarFile
from zipfile import ZipFile

from py7zr import SevenZipFile
from rarfile import RarFile

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.pdffile_stub import PDFFile


ArchiveType = ZipFile | RarFile | TarFile | SevenZipFile | PDFFile
