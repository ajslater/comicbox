"""Initialization mixin."""

from __future__ import annotations

import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tarfile import is_tarfile
from tarfile import open as tarfile_open
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from zipremove import ZipFile, is_zipfile

from comicbox._pdf import PDF_ENABLED
from comicbox.config.settings import ComicboxSettings
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import UnsupportedArchiveTypeError

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Callable, Mapping
    from datetime import datetime

    from pdffile import PDFFile
    from py7zr.io import BytesIOFactory

    from comicbox.box.archive.archiveinfo import InfoType
    from comicbox.box.types import ArchiveType
    from comicbox.formats import MetadataFormats
    from comicbox.formats.sources import MetadataSources
else:
    from comicbox._pdf import PDFFile


@dataclass
class SourceData:
    """Pre parsed source metadata."""

    data: str | bytes | Mapping
    path: Path | str | None = None
    fmt: MetadataFormats | None = None
    from_archive: bool = False


@dataclass
class LoadedMetadata:
    """Loaded Metadata."""

    metadata: Mapping
    path: Path | None = None
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
            raise FileNotFoundError(reason)
        if path.is_dir():
            reason = f"{path} is a directory."
            raise IsADirectoryError(reason)
        return path

    def __init__(
        self,
        path: Path | str | None = None,
        config: ComicboxSettings | Namespace | Mapping | None = None,
        metadata: Mapping | str | bytes | None = None,
        fmt: MetadataFormats | None = None,
    ) -> None:
        """
        Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a ComicboxSettings dataclass. If None, Comicbox generates its own from the
            environment.
        metadata: a comicbox-schema-shaped dict (the root-wrapped form, e.g.
            ``{"comicbox": {...}}``) to layer onto the metadata gathered from
            the path. A raw string/bytes blob in any supported format is
            also accepted (pass ``fmt`` to skip detection).
        fmt: the MetadataFormats member describing the format of ``metadata``;
            None means the comicbox format.

        Logging is never (re)configured here: comicbox is a library, and its
        modules log through whatever loguru sinks the host application
        configured. The comicbox CLI and worker entry points call
        ``comicbox.logger.init_logging`` themselves.
        """
        self._path = self._validate_path(path)
        if isinstance(config, ComicboxSettings):
            self._config: ComicboxSettings = config
        else:
            # Lazy import: comicbox.config imports comicbox.formats which
            # transitively imports this module — keep the top-level import
            # graph acyclic.
            from comicbox.config import get_config

            self._config = get_config(config, path=self._path, box=True)
        self._reset_archive(fmt, metadata)

    def _reset_loaded_forward_caches(self) -> None:
        self._merged_metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]
        # The _dict_formats context each cache below was computed under.
        # None is a wildcard: set_internal_metadata pins metadata for every
        # context. See get_internal_metadata / get_computed_metadata.
        self._computed_dict_formats: frozenset | None = frozenset()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._metadata_dict_formats: frozenset | None = frozenset()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._computed: tuple = ()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._extra_delete_keys: set = set()  # pyright: ignore[reportUninitializedInstanceVariable]
        self._computed_merged_metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]
        self._metadata: MappingProxyType = MappingProxyType({})  # pyright: ignore[reportUninitializedInstanceVariable]

    def _reset_archive(
        self, fmt: MetadataFormats | None, metadata: Mapping | str | bytes | None
    ) -> None:
        self._archive_cls: Callable | None = None
        self._file_type: FileTypeEnum | None = None
        self._set_archive_cls()
        self._archive: ArchiveType | None = None
        self._namelist: tuple[str, ...] | None = None
        self._infolist: tuple[InfoType, ...] | None = None
        self._7zfactory: BytesIOFactory | None = None

        self._transform_cache: dict = {}
        self._page_filenames: tuple[str, ...] | None = None
        self._cover_paths: tuple[str, ...] | None = None
        self._page_count: int | None = None

        from comicbox.formats.sources import MetadataSources

        self._sources: dict[
            MetadataSources, list[SourceData] | tuple[SourceData, ...]
        ] = {}
        if metadata:
            self._sources[MetadataSources.API] = [SourceData(metadata, fmt=fmt)]
        self._loaded: dict[MetadataSources, tuple[LoadedMetadata, ...]] = {}
        self._normalized: dict[MetadataSources, tuple[LoadedMetadata, ...]] = {}
        self._path_mtime_dttm: datetime | None = None
        self._dict_formats: frozenset[MetadataFormats] = frozenset()
        self._reset_loaded_forward_caches()

    @staticmethod
    def is_pdf_supported() -> bool:
        """Are PDFs supported."""
        return "pdffile" in sys.modules

    def _set_archive_cls_pdf(self) -> bool:
        """PDFFile is only optionally installed."""
        if not PDF_ENABLED:
            return self._archive_is_pdf
        with suppress(OSError):
            if PDFFile.is_pdffile(str(self._path)):
                # Both attributes get unconditional defaults at the top of
                # _set_archive_cls; the suppressions cover the documented
                # init-in-reset-method pattern, not a real lifecycle gap.
                self._archive_is_pdf = True  # pyright: ignore[reportUninitializedInstanceVariable]
                self._archive_cls = PDFFile
                self._pdf_suffix = PDFFile.SUFFIX  # pyright: ignore[reportUninitializedInstanceVariable]
        return self._archive_is_pdf

    def _try_detect_pdf(self, _path: Path) -> bool:
        if self._set_archive_cls_pdf():
            self._file_type = FileTypeEnum.PDF
            return True
        return False

    def _try_detect_7z(self, path: Path) -> bool:
        # py7zr is imported lazily — CB7 is rare and the package is heavy.
        from py7zr import SevenZipFile, is_7zfile

        if is_7zfile(path):
            self._archive_cls = SevenZipFile
            self._file_type = FileTypeEnum.CB7
            return True
        return False

    def _try_detect_zip(self, path: Path) -> bool:
        if is_zipfile(path):
            self._archive_cls = ZipFile
            self._file_type = FileTypeEnum.CBZ
            return True
        return False

    def _try_detect_rar(self, path: Path) -> bool:
        # rarfile is imported lazily — defers the heavy package init for
        # workers that only see CBZs (the common case at bulk-read scale).
        from rarfile import RarFile, is_rarfile

        if is_rarfile(path):
            self._archive_cls = RarFile
            self._file_type = FileTypeEnum.CBR
            return True
        return False

    def _try_detect_tar(self, path: Path) -> bool:
        if is_tarfile(path):
            self._archive_cls = tarfile_open
            self._file_type = FileTypeEnum.CBT
            return True
        return False

    # Full detection order (default when no extension hint)
    _FULL_DETECT_ORDER: tuple[str, ...] = ("pdf", "7z", "zip", "rar", "tar")

    # Extension → which types to try first (saves disk reads)
    _EXTENSION_HINT: ClassVar[dict[str, tuple[str, ...]]] = {
        ".cbz": ("zip",),
        ".cbr": ("rar",),
        ".cb7": ("7z",),
        ".cbt": ("tar",),
        ".pdf": ("pdf",),
    }

    def _try_detect(self, key: str, path: Path) -> bool:
        """Try a single archive type detection."""
        detectors = {
            "pdf": self._try_detect_pdf,
            "7z": self._try_detect_7z,
            "zip": self._try_detect_zip,
            "rar": self._try_detect_rar,
            "tar": self._try_detect_tar,
        }
        return detectors[key](path)

    def _detect_archive_cls(self, path: Path) -> None:
        """Try each detector in hint-first priority order; raise if none match."""
        suffix = path.suffix.lower()
        hinted = self._EXTENSION_HINT.get(suffix, ())
        remaining = tuple(k for k in self._FULL_DETECT_ORDER if k not in hinted)
        for key in hinted + remaining:
            if self._try_detect(key, path):
                return
        reason = f"Unsupported archive type: {path}"
        raise UnsupportedArchiveTypeError(reason)

    def _set_archive_cls(self) -> None:
        """Set the path and determine the archive type."""
        # Every attribute is assigned unconditionally before the early
        # return so a pathless box has a complete, safe attribute set.
        # The suppressions cover the documented init-in-reset-method
        # pattern (__init__ → _reset_archive → here), not a lifecycle gap.
        self._archive_is_pdf: bool = False
        self._pdf_suffix: str = ""
        self._info_size_attr: str = "file_size"  # pyright: ignore[reportUninitializedInstanceVariable]
        self._info_fn_attr: str = "filename"  # pyright: ignore[reportUninitializedInstanceVariable]
        if not self._path:
            return
        path = self._path

        self._detect_archive_cls(path)

        if self._archive_cls == tarfile_open:
            # Tarfile info objects use different attribute names.
            self._info_size_attr = "size"
            self._info_fn_attr = "name"

    def get_path(self) -> Path | None:
        """Get the path for the archive."""
        return self._path

    def get_file_type(self) -> str:
        """Return archive type string."""
        return self._file_type.value if self._file_type else ""
