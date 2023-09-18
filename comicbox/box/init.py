"""Initialization mixin."""
import stat
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tarfile import is_tarfile
from tarfile import open as tarfile_open
from typing import TYPE_CHECKING, Callable, Optional, Union
from zipfile import ZipFile, is_zipfile

from confuse import AttrDict
from rarfile import RarFile, is_rarfile

from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.schemas.comicbox_base import ComicboxBaseSchema, SchemaConfig
from comicbox.sources import MetadataSources
from pdffile.pdffile import PDFFile

if TYPE_CHECKING:
    from tarfile import TarFile


@dataclass
class SourceData:
    """Pre parsed source metadata."""

    metadata: Union[str, bytes, Mapping]
    schema_class: Optional[type[ComicboxBaseSchema]] = None
    path: Optional[str] = None


class ComicboxInitMixin:
    """Initialization mixin."""

    _MODE_EXECUTABLE = stat.S_IXUSR ^ stat.S_IXGRP ^ stat.S_IXOTH

    def __init__(
        self,
        path: Union[Path, str, None] = None,
        config: Union[AttrDict, Namespace, Mapping, None] = None,
        metadata: Optional[Mapping] = None,
    ):
        """Initialize the archive with a path to the archive.

        path: the path to the comic archive
        config: a confuse AttrDict. If None, Comicbox generates its own from the
            environment.
        metadata: a comicbox.schemas dict to use instead of gathering the metadata
            from the path.
        """
        self._path: Optional[Path] = Path(path) if path else None
        if self._path and not self._path.exists():
            reason = f"{self._path} does not exist."
            raise ValueError(reason)

        self._config: AttrDict = get_config(config)
        self._default_dump_config = SchemaConfig(stamp=True, tagger=self._config.tagger)

        self._reset_archive(metadata)

    def _reset_loaded_forward_caches(self):
        self._loaded_synth_metadata: dict = {}
        self._computed: tuple = ()
        self._computed_synthed_metadata: dict = {}
        self._metadata: dict = {}

    def _reset_archive(self, metadata):
        self._archive_cls: Optional[Callable] = None
        self._file_type: Optional[str] = None
        self._set_archive_cls()
        self._archive: Union[ZipFile, RarFile, TarFile, PDFFile, None] = None
        self._info_fn_attr = "name" if self._archive_cls == tarfile_open else "filename"
        self._info_size_attr = (
            "size" if self._archive_cls == tarfile_open else "file_size"
        )
        self._namelist = None
        self._infolist = None

        self._sources: dict = {}
        if metadata:
            self._sources[MetadataSources.API] = (
                SourceData(
                    metadata,
                    MetadataSources.API.value.schema_class,
                ),
            )
        self._parsed: dict = {}
        self._loaded: dict = {}

        self._reset_loaded_forward_caches()

        self._page_filenames = None
        self._cover_path_list = []
        self._page_count = None

    def _set_archive_cls(self):
        """Set the path and determine the archive type."""
        if not self._path:
            return
        if PDFFile.is_pdffile(self._path):
            # Important to have PDFile before zipfile
            self._archive_cls = PDFFile
            self._file_type = "PDF"
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
