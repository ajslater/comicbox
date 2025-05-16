"""Cli for comicbox."""

import sys
from argparse import Action, ArgumentParser, Namespace
from collections.abc import Sequence
from types import MappingProxyType

from rich import box
from rich import print as rich_print
from rich.console import Group
from rich.style import Style
from rich.styled import Styled
from rich.table import Table
from rich.text import Text
from rich_argparse import RichHelpFormatter
from typing_extensions import override

from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats import PDF_ENABLED, MetadataFormats
from comicbox.print import PrintPhases
from comicbox.run import Runner

_TABLE_ARGS = MappingProxyType(
    {
        "box": box.HEAVY,
        "border_style": "bright_black",
        "row_styles": ("", "on grey7"),
        "title_justify": "left",
    }
)
_HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError,)
_PRINT_PHASES_DESC = MappingProxyType(
    {
        "v": ("Software version", "v"),
        "t": ("File type", ""),
        "f": ("File names", "l"),
        "s": ("Source metadata", ""),
        "l": ("Loaded metadata sources", ""),
        "n": ("Loaded metadata normalized to comicbox schema", ""),
        "m": ("Merged normalized intermediate metadata", ""),
        "c": ("Computed metadata sources", ""),
        "p": ("Final metadata merged with computed sources", "p"),
    }
)
_METADATA_EXAMPLES = Styled(
    """
Metadata can be any tag from any of the supported metadata formats.
Complex [cyan]--metadata[/cyan] Examples:
  [cyan]-m[/cyan] 'Character: anna,bea,carol, contributors: {inker: [Other Name], writer: [Other Name, Writer Name]}, arcs: {Arc Name: 1, Other Arc Name: 5}'
  [cyan]-m[/cyan] '{publisher: My Press}'
  [cyan]-m[/cyan] \"Title: 'GI Robot: Foreign and Domestic'\"
  [cyan]-m[/cyan] \"series: 'Solarpunk: Kūchū Bōsōzoku'\"
""",
    style="argparse.text",
)
_DELETE_KEYS_EXAMPLES = Styled(
    """
Glom key paths are dot delimited. Numbers are list indexes. This deletes three comma delimited nested key paths:

  [cyan]-D[/cyan] [dark_cyan]series,arcs.Across the Multiverse.number,reprints.0.series[/dark_cyan]
    """,
    style="argparse.text",
)
_QUIET_LOGLEVEL = MappingProxyType({1: "INFO", 2: "SUCCESS", 3: "WARNING", 4: "ERROR"})


class CSVAction(Action):
    """Parse comma deliminated sequences."""

    @override
    def __call__(self, _parser, namespace, values, _string=None):
        """Parse comma delimited sequences."""
        if isinstance(values, str):
            values_array = values.split(",")
        elif isinstance(values, Sequence):
            values_array = values
        else:
            return
        setattr(namespace, self.dest, values_array)


class PageRangeAction(Action):
    """Parse page range."""

    @override
    def __call__(self, _parser, namespace, values, _string=None):
        """Parse page range delimited by :."""
        values_array = values.split(":")
        if not values_array:
            return

        index_from = int(values_array[0]) if len(values_array[0]) else None

        if len(values_array) == 1:
            index_to = index_from
        elif len(values_array[1]):
            index_to = int(values_array[1])
        else:
            index_to = None

        if index_from is not None:
            namespace.index_from = index_from
        if index_to is not None:
            namespace.index_to = index_to


def _get_help_print_phases_table():
    table = Table(title="[dark_cyan]PRINT_PHASE[/dark_cyan] characters", **_TABLE_ARGS)  # pyright: ignore[reportArgumentType]
    table.add_column("Phase", style="green")
    table.add_column("Description")
    table.add_column("Shortcut", style="cyan")
    for phase, attrs in _PRINT_PHASES_DESC.items():
        desc, shortcut = attrs
        if shortcut:
            shortcut = "-" + shortcut
        table.add_row(phase, desc, shortcut)
    return table


FORMAT_TITLE = """Format keys for [cyan]--ignore-read[/cyan], [cyan]--write[/cyan], and [cyan]--export[/cyan]\n
Formats shown in order of precedence. [dim]Dimmed[/dim] formats are not indented for distribution and are provided as convenience to developers."""


def _get_help_format_table():
    table = Table(title=FORMAT_TITLE, **_TABLE_ARGS)  # pyright: ignore[reportArgumentType]
    table.add_column("Format")
    table.add_column("Keys", style="green")
    for fmt in reversed(MetadataFormats):
        if not fmt.value.enabled:
            continue
        label = fmt.value.label
        if label.startswith(("ComicTagger", "Comicbox")):
            style = Style(dim=True)
            label = Text(label, style=style)
        keys = ", ".join(sorted(fmt.value.config_keys))
        table.add_row(label, keys)

    return table


def _add_option_group(parser):
    option_group = parser.add_argument_group("Options")
    option_group.add_argument(
        "-c",
        "--config",
        metavar="CONFIG_PATH",
        action="store",
        help="Path to an alternate config file.",
    )
    option_group.add_argument(
        "-r",
        "--read",
        action=CSVAction,
        metavar="FORMATS",
        dest="read",
        help="Read metadata formats. Defaults to all.",
    )
    option_group.add_argument(
        "--read-ignore",
        action=CSVAction,
        metavar="FORMATS",
        dest="read_ignore",
        help="Subtract these formats from the read formats.",
    )
    option_group.add_argument(
        "-m",
        "--metadata",
        dest="metadata_cli",
        metavar="YAML_METADATA",
        action="append",
        help=(
            "Set metadata fields with linear YAML. (e.g.: 'keyA: value,"
            " keyB: [valueA,valueB,valueC], keyC: {subkey: {subsubkey: value}')"
            " Place a space after colons so they are properly parsed as YAML key"
            " value pairs. If your value contains a special YAML character (e.g."
            " :[]{}) quote the value. Linear YAML delineates subkeys with curly"
            " brackets in place of indentation."
        ),
    )
    option_group.add_argument(
        "-D",
        "--delete-keys",
        action=CSVAction,
        help="Delete a comma delimited list of comicbox glom key paths entirely from the final metadata. Example below.",
    )
    option_group.add_argument(
        "-d",
        "--dest-path",
        help="destination path for extracting pages and metadata.",
    )
    option_group.add_argument(
        "--delete-orig",
        action="store_true",
        help="Delete the original cbr, cbt, or cb7 file if it was converted to a cbz successfully.",
    )
    option_group.add_argument(
        "--recurse",
        action="store_true",
        help="Perform selected actions recursively on a directory.",
    )
    option_group.add_argument(
        "-y",
        "--dry-run",
        action="store_true",
        help="Do not write anything to the filesystem. Report on what would be done.",
    )
    option_group.add_argument(
        "-G",
        "--no-compute-pages",
        dest="compute_pages",
        action="store_false",
        default=True,
        help=("Never compute page_count or pages metadata from the archive."),
    )
    option_group.add_argument(
        "-R",
        "--replace-metadata",
        action="store_true",
        default=False,
        help="Replace metadata keys instead of merging them.",
    )
    option_group.add_argument(
        "-Q",
        "--quiet",
        action="count",
        default=0,
        help=(
            "Increasingingly quiet success messages, warnings and errors with more Qs."
        ),
    )
    option_group.add_argument(
        "-s",
        "--stamp",
        dest="stamp",
        action="store_true",
        help="Normally comicbox will only update the notes (if enabled), tagger, and updated_at tags when performing a write or export action. This adds the stamps anyway.",
    )
    option_group.add_argument(
        "-N",
        "--no-stamp-notes",
        dest="stamp_notes",
        action="store_false",
        help=(
            "Do not write the notes field with tagger, timestamp and identifiers "
            "when writing metadata out to a file."
        ),
    )
    option_group.add_argument(
        "-t",
        "--theme",
        help="Pygments theme to use for syntax highlighting. https://pygments.org/styles/. 'none' will stop highlighting.",
    )


def _add_action_group(parser):
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "-P",
        "--print-phases",
        dest="print",
        metavar="PRINT_PHASES",
        action="store",
        default="",
        help=(
            "Print separate phases of metadata processing."
            " Specify with a string that contains phase characters"
            " listed below. e.g. -P slcm."
        ),
    )
    action_group.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Print software version. Shortcut for -P v",
    )
    action_group.add_argument(
        "-p",
        "--print",
        dest="print_metadata",
        action="store_true",
        help="Print merged metadata. Shortcut for -P d.",
    )
    action_group.add_argument(
        "-l",
        "--list",
        dest="print_filenames",
        action="store_true",
        help="Print filenames in archive. Shortcut for -P f.",
    )
    action_group.add_argument(
        "-i",
        "--import",
        action="append",
        dest="import_paths",
        help="Import metadata from external files.",
    )
    action_group.add_argument(
        "-x",
        "--export",
        metavar="FORMATS",
        action=CSVAction,
        help="Export metadata as external files to --dest-path. Format keys listed below.",
    )
    action_group.add_argument(
        "--delete-all-tags",
        action="store_true",
        help="Delete all tags from the archive. Overrides --write.",
    )
    action_group.add_argument(
        "-e",
        "--pages",
        action=PageRangeAction,
        help=(
            "Extract a single page or : delimited range of pages by zero based index"
            " to --dest-path."
        ),
    )
    action_group.add_argument(
        "-o", "--covers", action="store_true", help="Extract cover pages."
    )
    action_group.add_argument(
        "-z",
        "--cbz",
        action="store_true",
        help="Export the archive to CBZ format and rewrite all metadata formats found.",
    )
    action_group.add_argument(
        "-w",
        "--write",
        metavar="FORMATS",
        action=CSVAction,
        help=(
            "Write comic metadata formats to archive cbt & cbr are always"
            " exported to cbz format. Format keys listed below."
        ),
    )
    action_group.add_argument(
        "--rename",
        action="store_true",
        help="Rename the file with comicbox's filename format.",
    )
    action_group.add_argument(
        "-h", "--help", action="help", help="Show only this help message and exit"
    )


def _add_target_group(parser):
    target_group = parser.add_argument_group("Targets")
    target_group.add_argument(
        "paths",
        nargs="*",
        help="Paths to comic archives or directories",
    )


def get_args(params=None) -> Namespace:
    """Get arguments and options."""
    description = "Comic book archive multi format metadata read/write/transform tool and image extractor."
    if not PDF_ENABLED:
        description += "\n[yellow]Comicbox is not installed with PDF support.[/yellow]"

    epilog = Group(
        _get_help_print_phases_table(),
        _METADATA_EXAMPLES,
        _DELETE_KEYS_EXAMPLES,
        _get_help_format_table(),
    )

    parser = ArgumentParser(
        description=description,
        epilog=epilog,  # pyright: ignore[reportArgumentType]
        formatter_class=RichHelpFormatter,
        add_help=False,
    )
    _add_option_group(parser)
    _add_action_group(parser)
    _add_target_group(parser)

    if params is not None:
        params = params[1:]
    return parser.parse_args(params)


def post_process_args(cns):
    """Adjust CLI config."""
    # Print options
    if cns.version:
        cns.print += PrintPhases.VERSION.value
    if cns.print_filenames:
        cns.print += PrintPhases.FILE_NAMES.value
    if cns.print_metadata:
        cns.print += PrintPhases.METADATA.value

    # Loglevel
    if cns.quiet:
        cns.loglevel = _QUIET_LOGLEVEL.get(cns.quiet, "CRITICAL")


def main(params=None):
    """Get CLI arguments and perform the operation on the archive."""
    cns = get_args(params)
    post_process_args(cns)
    args = Namespace(comicbox=cns)

    runner = Runner(args)
    try:
        runner.run()
    except _HANDLED_EXCEPTIONS as exc:
        rich_print(f"[yellow]{exc}[/yellow]")
        sys.exit(1)
