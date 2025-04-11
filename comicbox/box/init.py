"""Initialization mixin."""

import stat
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tarfile import is_tarfile
from tarfile import open as tarfile_open
from types import MappingProxyType
from typing import TYPE_CHECKING
from zipfile import ZipFile, is_zipfile

from confuse import AttrDict
from py7zr import SevenZipFile, is_7zfile
from rarfile import RarFile, is_rarfile

from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.dummy import PDFFile

if TYPE_CHECKING:
    from tarfile import TarFile


@dataclass
class SourceData:
    """Pre parsed source metadata."""

    data: str | bytes | Mapping
    path: Path | str | None = None
    fmt: MetadataFormats | None = None
    from_archive: bool = False


class ComicboxInitMixin:
    """Initialization mixin."""

    _MODE_EXECUTABLE = stat.S_IXUSR ^ stat.S_IXGRP ^ stat.S_IXOTH

    def __init__(
        self,
        path: Path | str | None = None,
        config: AttrDict | Namespace | Mapping | None = None,
        metadata: Mapping | None = None,
        fmt: MetadataFormats | None = None,
    ):
        """
        Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a confuse AttrDict. If None, Comicbox generates its own from the
            environment.
        metadata: a comicbox.schemas dict to use instead of gathering the metadata
            from the path.
        """
        self._path: Path | None = Path(path) if path else None
        if self._path and not self._path.exists():
            reason = f"{self._path} does not exist."
            raise ValueError(reason)

        self._config: AttrDict = get_config(config)
        self._all_sources = None
        self._archive_is_pdf = False
        self._pdf_suffix = ""

        self._reset_archive(fmt, metadata)

    def _reset_loaded_forward_caches(self):
        self._merged_metadata: MappingProxyType = MappingProxyType({})
        self._computed: tuple = ()
        self._computed_merged_metadata: MappingProxyType = MappingProxyType({})
        self._metadata: MappingProxyType = MappingProxyType({})

    def _reset_archive(self, fmt: MetadataFormats | None, metadata: Mapping | None):
        self._archive_cls: Callable | None = None
        self._file_type: str | None = None
        self._set_archive_cls()
        try:
            # FUTURE Custom archive type possible in python 3.12
            self._archive: (
                ZipFile | RarFile | TarFile | SevenZipFile | PDFFile | None
            ) = None  # type: ignore[reportRedeclaration]
        except NameError:
            self._archive: (
                ZipFile | RarFile | TarFile | SevenZipFile | PDFFile | None
            ) = None
        self._info_fn_attr = "name" if self._archive_cls == tarfile_open else "filename"
        self._info_size_attr = (
            "size"
            if self._archive_cls == tarfile_open
            else None
            if self._archive_cls == SevenZipFile
            else "file_size"
        )
        self._namelist = None
        self._infolist = None

        self._sources: dict = {}
        if metadata:
            self._sources[MetadataSources.API] = [SourceData(metadata, fmt=fmt)]
        self._parsed: dict = {}
        self._loaded: dict = {}
        self._normalized: dict = {}

        self._reset_loaded_forward_caches()

        self._page_filenames = None
        self._cover_paths = ()
        self._page_count = None

    @staticmethod
    def is_pdf_supported() -> bool:
        """Are PDFs supported."""
        return "pdffile" in sys.modules

    def _set_archive_cls_pdf(self):
        """PDFFile is only optionally installed."""
        with suppress(NameError, OSError):
            self._archive_is_pdf = PDFFile.is_pdffile(self._path)  # type: ignore[reportPossiblyUnboundVariable]
            if self._archive_is_pdf:
                self._archive_cls = PDFFile  # type: ignore[reportPossiblyUnboundVariable]
                self._pdf_suffix = PDFFile.SUFFIX  # type: ignore[reportPossiblyUnboundVariable]
        return self._archive_is_pdf

    def _set_archive_cls(self):
        """Set the path and determine the archive type."""
        if not self._path:
            return

        if self._set_archive_cls_pdf():
            # Important to have PDFile before zipfile
            self._file_type = "PDF"
        elif is_7zfile(self._path):
            self._archive_cls = SevenZipFile
            self._file_type = "CB7"
        elif is_zipfile(self._path):
            self._archive_cls = ZipFile
            self._file_type = "CBZ"
        elif is_rarfile(self._path):
            self._archive_cls = RarFile
            self._file_type = "CBR"
        elif is_tarfile(self._path):
            self._archive_cls = tarfile_open
            self._file_type = "CBT"
        else:
            reason = f"Unsupported archive type: {self._path}"
            raise UnsupportedArchiveTypeError(reason)

    def get_path(self):
        """Get the path for the archive."""
        return self._path

    def get_file_type(self):
        """Return archive type string."""
        return self._file_type
