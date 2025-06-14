"""Getting and storing source metadata."""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from loguru import logger

from comicbox.box.archive import ComicboxArchive
from comicbox.box.init import SourceData
from comicbox.formats import MetadataFormats
from comicbox.schemas.pdf import MuPDFSchema
from comicbox.sources import MetadataSources

FILENAME_FORMAT_MAP = MappingProxyType(
    {
        fmt.value.filename.lower(): fmt
        for fmt in MetadataSources.ARCHIVE_FILE.value.formats
    }
)


class ComicboxSources(ComicboxArchive):
    """Getting and storing source metadata."""

    def _get_source_config_metadata(self):
        source_data_list = []
        if not self._config.metadata:
            return source_data_list
        fmt = self._config.metadata_format
        if fmt and fmt not in self._config.read:
            return source_data_list
        try:
            if isinstance(fmt, str):
                fmt = MetadataFormats[fmt.upper()]
            if not fmt or fmt in self._config.read:
                source_data_list = [SourceData(self._config.metadata, fmt=fmt)]
        except Exception as exc:
            logger.warning(f"Error reading metadata from config: {exc}")
        return source_data_list

    def _get_source_cli_metadata(self):
        """Get metadatas from cli."""
        source_data_list = []
        if not self._config.metadata_cli:
            return source_data_list
        for source_string in self._config.metadata_cli:
            try:
                sd = SourceData(source_string)
                source_data_list.append(sd)
            except Exception as exc:
                logger.warning(
                    f"Error reading metadata from cli '{source_string}': {exc}"
                )
        return source_data_list

    def _get_source_import_metadata(self):
        """Read multiple import paths into strings."""
        source_data_list = []
        paths = self._config.import_paths
        if not paths:
            return source_data_list
        for path_str in paths:
            try:
                path = Path(path_str)
                with path.open("r") as f:
                    source_string = f.read()
                fmt = FILENAME_FORMAT_MAP.get(path.name.lower())
                if not fmt or fmt in self._config.read:
                    sd = SourceData(source_string, path, fmt)
                    source_data_list.append(sd)
            except Exception as exc:
                logger.warning(
                    f"Error reading metadata from import path {path_str}: {exc}"
                )
                logger.exception("")
        return source_data_list

    def _get_source_filename_metadata(self):
        source_data_list = []
        if not self._path:
            return source_data_list
        try:
            for fmt in self._config.computed.read_filename_formats:
                source_data_list += [
                    SourceData(self._path.name, fmt=fmt, from_archive=True)
                ]
        except Exception as exc:
            logger.warning(
                f"Error reading metadata from archive filename {self._path}: {exc}"
            )
        return source_data_list

    def _get_source_comment_metadata(self):
        source_data_list = []
        if not self._path:
            return source_data_list
        try:
            # Only one archive comment format exists, so assume it.
            only_comment_format = MetadataSources.ARCHIVE_COMMENT.value.formats[0]
            formats = only_comment_format in self._config.read
            if formats and (comment := self._get_comment()):
                comment = comment.decode(errors="replace")
                source_data_list = [
                    SourceData(comment, from_archive=True, fmt=only_comment_format)
                ]
        except Exception as exc:
            logger.warning(f"Error reading archive comment from {self._path}: {exc}")
        return source_data_list

    def _get_source_pdf_metadata(self):
        source_data_list = []
        if not self._path:
            return source_data_list
        pdf_fmts = (
            frozenset(MetadataSources.ARCHIVE_PDF.value.formats) & self._config.read
        )
        if not pdf_fmts:
            return source_data_list
        try:
            archive = self._get_archive()
            if not archive or not self._archive_is_pdf:
                return source_data_list
            if md := archive.get_metadata():  # pyright: ignore[reportAttributeAccessIssue]
                md = MappingProxyType({MuPDFSchema.ROOT_TAG: md})
                source_data_list = [
                    SourceData(md, fmt=MetadataFormats.PDF, from_archive=True)
                ]
        except Exception as exc:
            logger.warning(f"Error reading from PDF header {self._path}: {exc}")
        return source_data_list

    def _store_top_source_archive_files(self, fn, files_dict):
        path = Path(fn)
        lower_name = path.name.lower()
        if (fmt := FILENAME_FORMAT_MAP.get(lower_name)) and fmt in self._config.read:
            old_entry = files_dict.get(fmt)
            path_level = len(path.parents)
            if not old_entry or old_entry[1] > path_level:
                files_dict[fmt] = (fn, path_level)

    def _add_top_source_archive_file(self, fmt, fn, source_data_list):
        source_string = self._archive_readfile(fn)
        sd = SourceData(source_string, Path(fn), fmt, from_archive=True)
        source_data_list.append(sd)

    def _get_source_archive_files_metadata(self):
        """Get source metadata from files in the archive."""
        # search filenames for metadata files and read.
        source_data_list = []
        if not self._path or not self._config.computed.read_file_formats:
            return source_data_list
        files_dict = {}
        for fn in self._get_archive_namelist():
            try:
                self._store_top_source_archive_files(fn, files_dict)
            except Exception as exc:
                logger.warning(f"Error reading {self._path}:{fn}: {exc}")

        for fmt, value in files_dict.items():
            fn = value[0]
            try:
                self._add_top_source_archive_file(fmt, fn, source_data_list)
            except Exception as exc:
                logger.warning(f"Error reading {self._path}:{fn}: {exc}")
        return source_data_list

    SOURCE_METHOD_MAP = MappingProxyType(
        {
            MetadataSources.CONFIG: _get_source_config_metadata,
            MetadataSources.CLI: _get_source_cli_metadata,
            MetadataSources.IMPORT_FILE: _get_source_import_metadata,
            MetadataSources.ARCHIVE_FILENAME: _get_source_filename_metadata,
            MetadataSources.ARCHIVE_COMMENT: _get_source_comment_metadata,
            MetadataSources.ARCHIVE_PDF: _get_source_pdf_metadata,
            MetadataSources.ARCHIVE_FILE: _get_source_archive_files_metadata,
        }
    )
    SOURCES_SET_ELSEWHERE = frozenset({MetadataSources.API, MetadataSources.EMBEDDED})

    def _set_source_metadata(self, source):
        """Set source metadata by source."""
        if self._config.delete_all_tags:
            return
        if source in self.SOURCES_SET_ELSEWHERE:
            # Set by init & add metadata below.
            return
        func = self.SOURCE_METHOD_MAP.get(source)
        if func:
            source_data_list = func(self)
        else:
            reason = f"{source} not a valid source metadata key."
            raise ValueError(reason)

        if source_data_list:
            source_data_list = tuple(source_data_list)
            self._sources[source] = source_data_list

    def get_source_metadata(self, source):
        """Get source metadata by key."""
        try:
            if source not in self._sources:
                self._set_source_metadata(source)
            return self._sources.get(source)
        except Exception as exc:
            logger.warning(
                f"{self._path} reading source metadata from {source.value.label}: {exc}"
            )

    def add_source(
        self,
        source: MetadataSources,
        metadata: str | bytes | Mapping,
        fmt: MetadataFormats | None = None,
        path: str | Path = "",
    ):
        """Add metadata directly to sources cache."""
        if source not in self._sources:
            self._sources[source] = []
        sd = SourceData(metadata, Path(path), fmt)
        self._sources[source].append(sd)

        # Clear forward caches
        self._parsed.pop(source, None)
        self._loaded.pop(source, None)
        self._reset_loaded_forward_caches()

    def add_metadata(self, metadata, fmt: MetadataFormats | None = None):
        """Add metadata directly to sources cache."""
        self.add_source(MetadataSources.API, metadata, fmt)

    def add_metadata_file(self, path: Path | str, fmt: MetadataFormats | None = None):
        """Add file contents to added sources."""
        path = Path(path)
        with path.open("r") as f:
            string = f.read()
        self.add_source(MetadataSources.IMPORT_FILE, string, fmt, path)
