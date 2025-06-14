"""Print Methods."""

from collections.abc import Mapping

from loguru import logger
from pygments.styles import get_style_by_name
from pygments.token import (
    Comment,
    Generic,
    Name,
    String,
)
from pygments.util import ClassNotFound
from rich.console import Console
from rich.pretty import Pretty
from rich.rule import Rule
from rich.style import Style
from rich.syntax import PygmentsSyntaxTheme, Syntax
from rich.table import Table
from rich.text import Text

from comicbox.box.archive import archive_close
from comicbox.box.dump_files import ComicboxDumpToFiles
from comicbox.print import PrintPhases
from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema
from comicbox.schemas.yaml import YamlRenderModule
from comicbox.sources import MetadataSources
from comicbox.version import VERSION

_SOURCES_LOADED_NORMALIZED = frozenset(
    {PrintPhases.SOURCE, PrintPhases.LOADED, PrintPhases.NORMALIZED}
)
_FILE_RULE_CHAR = "═"
DEFAULT_STYLE_NAME = "gruvbox-dark"
MASK_STYLE = Style(bgcolor="default")


def _make_style(theme, token):
    return theme.get_style_for_token(token) + MASK_STYLE


class ComicboxStyle:
    """Rich style definitions."""

    def __init__(self, style_name: str):
        """Initialize styles by theme."""
        if not style_name:
            self.section_header = Style()
            self.file_header = Style()
            self.path = Style()
            self.in_archive_path = Style()
            self.format = Style()
            self.subtitle = Style()
            self.section = Style()
        else:
            theme = PygmentsSyntaxTheme(style_name)

            self.section_header = _make_style(theme, Name.Builtin)
            self.file_header = self.section_header
            if style_name == DEFAULT_STYLE_NAME:
                self.path = Style(color="cyan")
                self.in_archive_path = Style(color="cyan", bold=True)
            else:
                self.path = _make_style(theme, Generic.Output)
                self.in_archive_path = _make_style(theme, Generic.Heading)
            self.format = _make_style(theme, Name.Attribute)
            self.subtitle = _make_style(theme, String)
            self.section = _make_style(theme, Comment)


class ComicboxPrint(ComicboxDumpToFiles):
    """Print Methods."""

    _CONSOLE = Console()

    def _set_pygments_style(self):
        style_name = self._config.theme
        if not style_name:
            style_name = DEFAULT_STYLE_NAME
        elif style_name.lower() == "none":
            self._pygments_style_name = ""
            return
        try:
            get_style_by_name(style_name)
        except ClassNotFound as exc:
            logger.warning(exc)
            style_name = DEFAULT_STYLE_NAME
        self._pygments_style_name = style_name

    def __init__(self, *args, **kwargs):
        """Set print variables."""
        super().__init__(*args, **kwargs)
        self._set_pygments_style()
        self._style = ComicboxStyle(self._pygments_style_name)

    def _syntax(self, code: str, lexer: str):
        """Apply rich syntax highlighting to code."""
        return (
            Syntax(
                code,
                lexer,
                theme=self._pygments_style_name,
                background_color="default",
                word_wrap=True,
            )
            if self._pygments_style_name
            else code
        )

    def _print(self, renderable):
        if self._pygments_style_name:
            self._CONSOLE.print(renderable)
        else:
            print(renderable)  # noqa: T201

    def print_section(self, title, renderable, subtitle=""):
        """Pretty print a titled rule over a renderable."""
        if subtitle:
            title += Text(": ") + Text(subtitle, style=self._style.subtitle)

        self._CONSOLE.print(Rule(style=self._style.section_header))
        self._CONSOLE.print(title)
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
        title = Text(str(self._path), style=self._style.path)
        self._CONSOLE.print(
            Rule(style=self._style.file_header, characters=_FILE_RULE_CHAR)
        )
        self._CONSOLE.print(title)

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
        path = Text(path, style=self._style.path)
        if source_data.path or source == MetadataSources.ARCHIVE_COMMENT:
            in_archive_path = (
                "(comment)"
                if source == MetadataSources.ARCHIVE_COMMENT
                else source_data.path
            )
            path += Text(":") + Text(
                str(in_archive_path), style=self._style.in_archive_path
            )
        title_parts = [Text(title, style=self._style.section)]
        if path:
            title_parts.append(path)
        if source_data.fmt:
            title_parts.extend(
                [
                    Text(format_preposition, style=self._style.section),
                    Text(source_data.fmt.value.label, style=self._style.format),
                ]
            )
        title = Text("")
        first = True
        for part in title_parts:
            if not first:
                title += Text(" ")
            title += part
            first = False
        return title

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
                renderable = Pretty(dict(md)) if self._pygments_style_name else md
            else:
                print_md = md.decode(errors="replace") if isinstance(md, bytes) else md
                lexer = fmt.value.lexer if (fmt := source_data.fmt) else ""
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
        title = Text("Merged for Compute")
        self.print_section(title, syntax)

    def _print_computed(self, schema):
        """Print computed metadata."""
        if PrintPhases.COMPUTED not in self._config.print:
            return
        computed = self.get_computed_metadata()
        for computed_md in computed:
            if not computed_md or not computed_md.metadata:
                continue
            # For delete keys
            dump = bool(computed_md.merger)
            str_data = schema.dumps(
                computed_md.metadata,
                dump=dump,
            )
            syntax = self._syntax(str_data, "yaml")
            self.print_section(Text("Computed"), syntax, subtitle=computed_md.label)

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
