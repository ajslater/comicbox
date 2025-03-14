"""Print Methods."""

from collections.abc import Mapping

from rich.console import Console
from rich.default_styles import DEFAULT_STYLES
from rich.pretty import Pretty
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table

from comicbox.box.archive_read import archive_close
from comicbox.box.metadata import ComicboxMetadataMixin
from comicbox.print import PrintPhases
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.schemas.yaml import YamlRenderModule
from comicbox.sources import MetadataSources
from comicbox.version import VERSION

_SOURCES_LOADED_NORMALIZED = frozenset(
    {PrintPhases.SOURCE, PrintPhases.LOADED, PrintPhases.NORMALIZED}
)


class ComicboxPrintMixin(ComicboxMetadataMixin):
    """Print Methods."""

    _HEADER_WIDTH = 5
    _TERM_WIDTH = 80
    _CONSOLE = Console()
    _RULE_CHAR = "⎯"
    _RULE_COLOR = DEFAULT_STYLES["rule.line"].color.name  # type: ignore[reportOptionalMemberAccess]
    _RULE_HEAD = f" [{_RULE_COLOR}]{_RULE_CHAR}[/{_RULE_COLOR}] "
    _FILE_RULE_CHAR = "═"
    _FILE_RULE_HEAD = f" [{_RULE_COLOR}]{_FILE_RULE_CHAR}[/{_RULE_COLOR}] "

    def _is_themed(self):
        """Use rich printing for code or not."""
        return self._config.theme and self._config.theme.lower() != "none"

    def _syntax(self, code: str, lexer: str):
        """Apply rich syntax highlighting to code."""
        return (
            Syntax(code, lexer, theme=self._config.theme, background_color="black")
            if self._is_themed()
            else code
        )

    def _print(self, renderable):
        if self._is_themed():
            self._CONSOLE.print(renderable)
        else:
            print(renderable)  # noqa: T201

    def print_section(self, title, renderable, subtitle=""):
        """Pretty print a titled rule over a renderable."""
        if subtitle:
            title += f": {subtitle}"

        title = self._RULE_HEAD + title
        rule = Rule(title, align="left", characters=self._RULE_CHAR)
        self._CONSOLE.print(rule)
        self._print(renderable)

    def _print_version(self):
        """Print package version."""
        if PrintPhases.VERSION not in self._config.print:
            return
        self._print(VERSION)

    def print_file_header(self):
        """Print header for this Archive's path."""
        if not self._path:
            return
        title = self._FILE_RULE_HEAD + str(self._path)
        rule = Rule(title, align="left", characters=self._FILE_RULE_CHAR)
        self._CONSOLE.print(rule)

    def _print_file_type(self):
        """Print the file type."""
        if PrintPhases.FILE_TYPE not in self._config.print:
            return
        ft = self.get_file_type()
        self._print(ft)

    def _print_file_names(self):
        """Print archive namelist."""
        if PrintPhases.FILE_NAMES not in self._config.print:
            return
        namelist = self._get_archive_namelist()
        pagenames = self.get_page_filenames()
        table = Table(style="cyan")
        table.add_column("Page")
        table.add_column("Archive Path")
        for name in namelist:
            try:
                index = str(pagenames.index(name))
            except Exception:
                index = ""
            index = index.rjust(3)
            table.add_row(index, name)
        self._CONSOLE.print(table)

    def _add_source_to_title(self, title, source, source_data, format_preposition="as"):
        path = str(self._path) if source.value.from_archive else ""
        if source_data.path:
            path += f":{source_data.path}"
        title_parts = [title]
        if path:
            title_parts.append(path)
        if source_data.fmt:
            title_parts.extend([format_preposition, source_data.fmt.value.label])
        return " ".join(title_parts)

    def _print_sources(self, source):
        """Print source metadtata."""
        source_data_list = self.get_source_metadata(source)
        if not source_data_list:
            return
        for source_data in source_data_list:
            if not source_data or not source_data.data:
                continue
            md = source_data.data
            if isinstance(md, Mapping):
                renderable = Pretty(dict(md)) if self._is_themed() else md
            else:
                print_md = md.decode(errors="replace") if isinstance(md, bytes) else md
                lexer = source_data.fmt.value.lexer if source_data.fmt else ""
                renderable = self._syntax(print_md, lexer)
            title = self._add_source_to_title(
                f"Source {source.value.label}", source, source_data
            )
            self.print_section(title, renderable)

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
            str_data = YamlRenderModule.dumps(dict(loaded_md.metadata))
            str_data = str_data.removesuffix("\n")
            syntax = self._syntax(str_data, "yaml")
            title = self._add_source_to_title(
                f"Loaded {source.value.label}", source, loaded_md
            )

            self.print_section(title, syntax)

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
            schema = ComicboxYamlSchema(path=normalized_md.path)
            str_data = schema.dumps(normalized_md.metadata)
            str_data = str_data.removesuffix("\n")
            syntax = self._syntax(str_data, "yaml")
            title = self._add_source_to_title(
                f"Normalized {source.value.label}",
                source,
                normalized_md,
                format_preposition="from",
            )

            self.print_section(title, syntax)

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
        str_data = schema.dumps(md)
        syntax = self._syntax(str_data, "yaml")
        title = "Merged for Compute"
        self.print_section(title, syntax)

    def _print_computed(self, schema):
        """Print computed metadata."""
        if PrintPhases.COMPUTED not in self._config.print:
            return
        computed = self.get_computed_metadata()
        for computed_md in computed:
            if not computed_md or not computed_md.metadata:
                continue
            str_data = schema.dumps(
                computed_md.metadata, allowed_null_keys=computed_md.allowed_null_keys
            )
            syntax = self._syntax(str_data, "yaml")
            self.print_section("Computed", syntax, subtitle=computed_md.label)

    def _print_metadata(self):
        """Pretty print the metadata."""
        if (
            PrintPhases.METADATA in self._config.print
            or PrintPhases.METADATA_OLD in self._config.print
        ):
            md = self.to_string()
            syntax = self._syntax(md, "yaml")
            self.print_section("Merged Metadata", syntax)

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
