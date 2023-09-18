""""Getting and storing source metadata."""
from logging import getLogger
from pathlib import Path

from comicbox.box.init import SourceData
from comicbox.box.page_filenames import ComicboxPageFilenamesMixin
from comicbox.sources import MetadataSources, SourceFrom
from pdffile.pdffile import PDFFile

LOG = getLogger(__name__)


class ComicboxSourcesMixin(ComicboxPageFilenamesMixin):
    """Getting and storing source metadata."""

    def _get_source_files_metadata(self, schema_class):
        """Get source metadata from files in the archive."""
        filename_lower = schema_class.FILENAME.lower()

        # search filenames for metadata files and read.
        source_data_list = []
        try:
            for fn in self._get_archive_namelist():
                lower_name = Path(fn).name.lower()
                if filename_lower == lower_name:
                    source_string = self._archive_readfile(fn)
                    sd = SourceData(source_string, schema_class, fn)
                    source_data_list.append(sd)
        except Exception as exc:
            LOG.warning(f"Error reading {self._path}: {exc}")
        if source_data_list:
            return tuple(source_data_list)
        return None

    def _get_source_filename_metadata(self, schema_class):
        if not self._path:
            return None
        md = self._path.name
        if not md:
            return None
        return (SourceData(md, schema_class, str(self._path)),)

    def _get_source_pdf_metadata(self, schema_class):
        if self._archive_cls != PDFFile:
            return None
        archive = self._get_archive()
        if not isinstance(archive, PDFFile):
            return None
        md = archive.get_metadata()
        if md:
            return (SourceData(md, schema_class, str(self._path)),)
        return None

    def _get_source_cbi_metadata(self, schema_class):
        comment = self._get_comment()
        if comment:
            return (SourceData(comment, schema_class),)
        return None

    def _get_source_import_metadata(self):
        """Read multiple import paths into strings."""
        paths = self._config.import_paths
        if not paths:
            return None
        source_metadata_list = []
        for path in paths:
            with Path(path).open("r") as f:
                source_string = f.read()
            sd = SourceData(source_string, None, path)
            source_metadata_list.append(sd)
        return tuple(source_metadata_list)

    def _get_source_file_metadata(self, source):
        if not self._archive_cls or not self._path:
            return None
        schema_class = source.value.schema_class
        if source.value.from_archive == SourceFrom.ARCHIVE_FILE:
            source_data_list = self._get_source_files_metadata(schema_class)
        elif source == MetadataSources.FILENAME:
            source_data_list = self._get_source_filename_metadata(schema_class)
        elif source == MetadataSources.PDF:
            source_data_list = self._get_source_pdf_metadata(schema_class)
        elif source == MetadataSources.CBI:
            source_data_list = self._get_source_cbi_metadata(schema_class)
        else:
            reason = f"{source} not a valid source metadata key."
            raise ValueError(reason)

        return source_data_list

    def _get_source_config_metadata(self, schema_class):
        if self._config.metadata:
            return (SourceData(self._config.metadata, schema_class),)
        return None

    def _get_cli_metadata(self, schema_class):
        """Get metadatas from cli."""
        if not self._config.metadata_cli:
            return None
        source_data_list = []
        for source_string in self._config.metadata_cli:
            sd = SourceData(source_string, schema_class)
            source_data_list.append(sd)
        if source_data_list:
            return tuple(source_data_list)
        return None

    def _set_source_metadata(self, source):
        """Set source metadata by source."""
        if source.value.from_archive.value > SourceFrom.OTHER.value:
            source_data_list = self._get_source_file_metadata(source)
        elif source == MetadataSources.CONFIG:
            schema_class = source.value.schema_class
            source_data_list = self._get_source_config_metadata(schema_class)
        elif source == MetadataSources.CLI:
            schema_class = source.value.schema_class
            source_data_list = self._get_cli_metadata(schema_class)
        elif source == MetadataSources.IMPORT:
            source_data_list = self._get_source_import_metadata()
        elif source in frozenset({MetadataSources.API, MetadataSources.ADDED}):
            return
        else:
            reason = f"{source} not a valid source metadata key."
            raise ValueError(reason)

        if source_data_list:
            source_data_list = tuple(source_data_list)
        self._sources[source] = source_data_list

    def get_source_metadata(self, source):
        """Get source metadata by key."""
        try:
            if source not in self._sources and source in self._config.read:
                self._set_source_metadata(source)
            return self._sources.get(source)
        except Exception as exc:
            LOG.warning(
                f"{self._path} reading source metadata from {source.value.label}: {exc}"
            )

    def add_source(self, metadata, schema_class=None, path=None):
        """Add metadata directly to sources cache."""
        if MetadataSources.ADDED not in self._sources:
            self._sources[MetadataSources.ADDED] = []
        sd = SourceData(metadata, schema_class, path)
        self._sources[MetadataSources.ADDED].append(sd)

        # Clear forward caches
        self._parsed.pop(MetadataSources.ADDED, None)
        self._loaded.pop(MetadataSources.ADDED, None)
        self._reset_loaded_forward_caches()

    def add_file_source(self, path, schema_class=None):
        """Add file contents to added sources."""
        path = Path(path)
        with path.open("r") as f:
            s = f.read()
        self.add_source(s, schema_class, path=path)
