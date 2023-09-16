"""Print Methods."""
from pprint import pprint

from comicbox.box.archive_read import archive_close
from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.print import PrintPhases
from comicbox.schemas.yaml import ComicboxYamlSchema, YamlRenderModule
from comicbox.sources import MetadataSources
from comicbox.version import VERSION

_SOURCES_PARSED_LOADED = frozenset(
    {PrintPhases.SOURCE, PrintPhases.PARSED, PrintPhases.LOADED}
)


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

    def _print_parsed(self, source):
        """Print parsed metadata."""
        # This is is a hack to get parsed
        parsed_md_list = self.get_parsed_metadata(source)
        if not parsed_md_list:
            return
        for parsed_md in parsed_md_list:
            if not parsed_md:
                continue
            self._print_header("Parsed", source.value.label, parsed_md.path)
            str_data = YamlRenderModule.dumps(parsed_md.metadata)
            if str_data.endswith("\n"):
                str_data = str_data[:-1]
            print(str_data)

    def _print_loaded(self, source, schema):
        """Print parsed metadata."""
        if PrintPhases.LOADED not in self._config.print:
            return
        loaded_md_list = self.get_loaded_metadata(source)
        if not loaded_md_list:
            return
        for loaded_md in loaded_md_list:
            if not loaded_md:
                continue
            self._print_header("Loaded", source.value.label, loaded_md.path)
            str_data = schema.dumps(loaded_md.metadata)
            if str_data.endswith("\n"):
                str_data = str_data[:-1]
            print(str_data)

    def _print_sources_parsed_loaded(self, schema):
        """Print sources, parsed and loaded metadata."""
        if not _SOURCES_PARSED_LOADED & self._config.print:
            return
        for source in MetadataSources:
            if PrintPhases.SOURCE in self._config.print:
                self._print_sources(source)
            if PrintPhases.PARSED in self._config.print:
                self._print_parsed(source)
            if PrintPhases.LOADED in self._config.print:
                self._print_loaded(source, schema)

    def _print_loaded_synthed(self, schema):
        if PrintPhases.LOADED_SYNTHED not in self._config.print:
            return
        md = self.get_loaded_synthed_metadata()
        self._print_header("Loaded Synthesized (Not Final)")
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
            str_data = schema.dumps(computed_md.metadata)
            print(str_data)

    def _print_metadata(self):
        """Pretty print the metadata."""
        if PrintPhases.METADATA in self._config.print:
            if len(self._config.print) > 1:
                self._print_header("Synthesized", "Metadata")
            md = self.to_string()
            print(md)

    @archive_close
    def print_out(self):
        """Print selections from config.print."""
        self._print_version()
        self._print_file_type()
        self._print_file_names()
        schema = ComicboxYamlSchema(path=self._path)
        self._print_sources_parsed_loaded(schema)
        self._print_loaded_synthed(schema)
        self._print_computed(schema)
        self._print_metadata()
