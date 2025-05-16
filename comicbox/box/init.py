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
from comicbox.config.frozenattrdict import FrozenAttrDict
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import MetadataFormats
from comicbox.logger import init_logging
from comicbox.sources import MetadataSources

try:
    from pdffile import PDFFile
except ImportError:
    from comicbox.box.pdffile_stub import PDFFile

if TYPE_CHECKING:
    from datetime import datetime

    from py7zr.io import BytesIOFactory

    from comicbox.box.types import ArchiveType


@dataclass
class SourceData:
    """Pre parsed source metadata."""

    data: str | bytes | Mapping
    path: Path | str | None = None
    fmt: MetadataFormats | None = None
    from_archive: bool = False


class ComicboxInit:
    """Initialization mixin."""

    _MODE_EXECUTABLE = stat.S_IXUSR ^ stat.S_IXGRP ^ stat.S_IXOTH

    def _validate_path(self, path: Path | str | None) -> Path | None:
        path = Path(path) if path else None
        if not path:
            return path
        if not path.exists():
            reason = f"{path} does not exist."
            raise ValueError(reason)
        if path.is_dir():
            reason = f"{path} is a directory."
            raise ValueError(reason)
        return path

    def __init__(
        self,
        path: Path | str | None = None,
        config: AttrDict | Namespace | Mapping | None = None,
        metadata: Mapping | None = None,
        fmt: MetadataFormats | None = None,
        logger=None,
    ):
        """
        Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a confuse AttrDict. If None, Comicbox generates its own from the
            environment.
        metadata: a comicbox.schemas dict to use instead of gathering the metadata
            from the path.
        """
        self._path = self._validate_path(path)
        self._config: FrozenAttrDict = FrozenAttrDict(
            get_config(config, path=self._path, box=True)
        )
        init_logging(self._config.loglevel, logger)
        self._reset_archive(fmt, metadata)

    def _reset_loaded_forward_caches(self):
        self._merged_metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]
        self._computed: tuple = ()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._extra_delete_keys: set = set()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._computed_merged_metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]
        self._metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]

    def _reset_archive(self, fmt: MetadataFormats | None, metadata: Mapping | None):
        self._archive_cls: Callable | None = None
        self._file_type: str | None = None
        self._set_archive_cls()
        self._archive: ArchiveType | None = None
        self._namelist: tuple[str, ...] | None = None
        self._infolist: tuple | None = None
        self._7zfactory: BytesIOFactory | None = None
        self._close_fd = self._config.close_fd

        self._page_filenames: tuple[str, ...] | None = None
        self._cover_paths: tuple[str, ...] | None = None
        self._page_count: int | None = None

        self._sources: dict = {}
        if metadata:
            self._sources[MetadataSources.API] = [SourceData(metadata, fmt=fmt)]
        self._parsed: dict = {}
        self._loaded: dict = {}
        self._normalized: dict = {}
        self._path_mtime_dttm: datetime | None = None
        self._reset_loaded_forward_caches()

    @staticmethod
    def is_pdf_supported() -> bool:
        """Are PDFs supported."""
        return "pdffile" in sys.modules

    def _set_archive_cls_pdf(self):
        """PDFFile is only optionally installed."""
        with suppress(NameError, OSError):
            if PDFFile.is_pdffile(str(self._path)):
                self._archive_is_pdf = True  # pyright: ignore[reportUninitializedInstanceVariable]
                self._archive_cls = PDFFile
                self._pdf_suffix = PDFFile.SUFFIX  # pyright: ignore[reportUninitializedInstanceVariable]
        return self._archive_is_pdf

    def _set_archive_cls(self):
        """Set the path and determine the archive type."""
        if not self._path:
            return

        self._archive_is_pdf: bool = False
        self._pdf_suffix: str = ""

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

        self._info_size_attr = (  # pyright: ignore[reportUninitializedInstanceVariable]
            "size" if self._archive_cls == tarfile_open else "file_size"
        )
        self._info_fn_attr = "name" if self._archive_cls == tarfile_open else "filename"  # pyright: ignore[reportUninitializedInstanceVariable]

    def get_path(self):
        """Get the path for the archive."""
        return self._path

    def get_file_type(self):
        """Return archive type string."""
        return self._file_type
