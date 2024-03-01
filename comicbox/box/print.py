"""Print Methods."""

from pprint import pprint

from comicbox.box.archive_read import archive_close
from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.print import PrintPhases
from comicbox.schemas.comicbox_mixin import PAGES_KEY
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.schemas.yaml import YamlRenderModule
from comicbox.sources import MetadataSources
from comicbox.version import VERSION

_SOURCES_LOADED_NORMALIZED = frozenset(
    {PrintPhases.SOURCE, PrintPhases.LOADED, PrintPhases.NORMALIZED}
)
_ALLOWED_NULL_KEYS = frozenset({PAGES_KEY})


class ComicboxPrintMixin(ComicboxMetadataMixin):
    """Print Methods."""

    _HEADER_WIDTH = 5
    _TERM_WIDTH = 80

    def _print_version(self):
        """Print package version."""
        if PrintPhases.VERSION not in self._config.print:
            return
        print(VERSION)

    def _print_file_type(self):
        """Print the file type."""
        if PrintPhases.FILE_TYPE not in self._config.print:
            return
        print(self.get_file_type())

    def _print_file_names(self):
        """Print archive namelist."""
        if PrintPhases.FILE_NAMES not in self._config.print:
            return
        namelist = self._get_archive_namelist()
        pagenames = self.get_page_filenames()
        print("Page\tArchive Path")
        for name in namelist:
            try:
                index = str(pagenames.index(name))
            except Exception:
                index = ""
            index = index.rjust(3)
            print(f"{index}\t{name}")

    @classmethod
    def _print_header(cls, prefix=None, label=None, path=None, char="-"):
        """Print a header."""
        first_part_list = [char * cls._HEADER_WIDTH, prefix, label]
        if path:
            first_part_list.append(path)

        first_part = " ".join(filter(None, first_part_list)) + " "
        end_len = cls._TERM_WIDTH - len(first_part)
        print(first_part + char * end_len)

    def print_file_header(self):
        """Print header for this Archive's path."""
        if not self._path:
            return
        self._print_header(path=str(self._path), char="=")

    def _print_sources(self, source):
        """Print source metadtata."""
        source_data_list = self.get_source_metadata(source)
        if not source_data_list:
            return
        for source_data in source_data_list:
            if not source_data or not source_data.metadata:
                continue
            self._print_header("Source", source.value.label, source_data.path)
            md = source_data.metadata
            if isinstance(md, dict):
                pprint(md)
            else:
                print_md = md.decode(errors="replace") if isinstance(md, bytes) else md
                print(print_md)

    def _print_loaded(self, source):
        """Print loaded metadata."""
        if PrintPhases.LOADED not in self._config.print:
            return
        loaded_md_list = self.get_loaded_metadata(source)
        if not loaded_md_list:
            return
        for loaded_md in loaded_md_list:
            if not loaded_md:
                continue
            self._print_header("Loaded", source.value.label, loaded_md.path)
            str_data = YamlRenderModule.dumps(dict(loaded_md.metadata))
            if str_data.endswith("\n"):
                str_data = str_data[:-1]
            print(str_data)

    def _print_normalized(self, source):
        """Print normalized metadata."""
        if PrintPhases.NORMALIZED not in self._config.print:
            return
        normalized_md_list = self.get_normalized_metadata(source)
        if not normalized_md_list:
            return
        for normalized_md in normalized_md_list:
            if not normalized_md:
                continue
            self._print_header("Normalized", source.value.label, normalized_md.path)
            schema = ComicboxYamlSchema(path=normalized_md.path)
            str_data = schema.dumps(normalized_md.metadata)
            if str_data.endswith("\n"):
                str_data = str_data[:-1]
            print(str_data)

    def _print_sources_loaded_normalized(self):
        """Print sources, loaded, and normalized metadata."""
        if not _SOURCES_LOADED_NORMALIZED & self._config.print:
            return
        for source in MetadataSources:
            if PrintPhases.SOURCE in self._config.print:
                self._print_sources(source)
            if PrintPhases.LOADED in self._config.print:
                self._print_loaded(source)
            if PrintPhases.NORMALIZED in self._config.print:
                self._print_normalized(source)

    def _print_merged(self, schema):
        if PrintPhases.MERGED not in self._config.print:
            return
        md = self.get_merged_metadata()
        self._print_header("Normalized Merged (Not Final)")
        str_data = schema.dumps(md)
        print(str_data)

    def _print_computed(self, schema):
        """Print parsed metadata."""
        if PrintPhases.COMPUTED not in self._config.print:
            return
        computed = self.get_computed_metadata()
        for computed_md in computed:
            if not computed_md or not computed_md.metadata:
                continue
            self._print_header("Computed", computed_md.label)
            str_data = schema.dumps(
                computed_md.metadata, allowed_null_keys=_ALLOWED_NULL_KEYS
            )
            print(str_data)

    def _print_metadata(self):
        """Pretty print the metadata."""
        if PrintPhases.METADATA in self._config.print:
            if len(self._config.print) > 1:
                self._print_header("Merged", "Metadata")
            md = self.to_string()
            print(md)

    @archive_close
    def print_out(self):
        """Print selections from config.print."""
        self._print_version()
        self._print_file_type()
        self._print_file_names()
        self._print_sources_loaded_normalized()
        schema = ComicboxYamlSchema(path=self._path)
        self._print_merged(schema)
        self._print_computed(schema)
        self._print_metadata()
