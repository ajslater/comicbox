"""Cli for comicbox."""
import sys
from argparse import Action, ArgumentParser, Namespace, RawDescriptionHelpFormatter
from collections.abc import Sequence
from logging import INFO

from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.print import PrintPhases
from comicbox.run import Runner
from comicbox.sources import MetadataSources

HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError,)


class CSVAction(Action):
    """Parse comma deliminated sequences."""

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


def map_keys(config, prefix, list_key, maps, value):
    """Map keyed values to config booleans."""
    key_list = getattr(config, list_key)
    if key_list:
        for key in key_list:
            lower_key = key.lower()
            for attr_suffix, parser_class in maps.items():
                if lower_key in parser_class.CONFIG_KEYS:
                    attr = f"{prefix}_{attr_suffix}"
                    setattr(config, attr, value)
    delattr(config, list_key)


def _create_format_help():
    lines = ""
    max_space = max(len(source.value.label) for source in MetadataSources) + 1
    for source in MetadataSources:
        if not source.value.configurable:
            continue
        label = source.value.label
        keys = ", ".join(source.value.schema_class.CONFIG_KEYS)
        space = (max_space - len(label)) * " "
        lines += f"  {label}:{space}{keys}"
        if not source.value.writable:
            lines += " (read only)"
        lines += "\n"

    return lines


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
        "-I",
        "--ignore-read",
        action=CSVAction,
        metavar="FORMATS",
        dest="ignore_read",
        help="Ignore reading metadata formats. List of format keys.",
    )
    option_group.add_argument(
        "-m",
        "--metadata",
        dest="metadata_cli",
        action="append",
        help="Set metadata fields key=value, key=valueA,valueB,valueC,"
        "key=subkey:value,subkey:value",
    )
    option_group.add_argument(
        "-d",
        "--dest-path",
        help="destination path for extracting pages and metadata.",
    )
    option_group.add_argument(
        "--delete-orig",
        action="store_true",
        help="Delete the original file if it was converted to a cbz successfully.",
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
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Increasingingly quiet success messages, "
        "warnings and errors with more qs.",
    )


def _add_action_group(parser):
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Print software version. Shortcut for (-n v)",
    )
    action_group.add_argument(
        "-p",
        "--print",
        dest="print_metadata",
        action="store_true",
        help="Print synthesized metadata. Shortcut for (-n m).",
    )
    action_group.add_argument(
        "-l",
        "--list",
        dest="print_filenames",
        action="store_true",
        help="Print filenames in archive. Shortcut for (-n n).",
    )
    action_group.add_argument(
        "-n",
        "--print-phases",
        dest="print",
        metavar="PHASES",
        action="store",
        default="",
        help=(
            "Print separate phases of metadata processing."
            " Specify with a string that contains phase characters"
            " listed below. e.g. -n slcm"
        ),
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
        help="Export metadata as external files to --dest-path.",
    )
    action_group.add_argument(
        "--delete-tags", action="store_true", help="Delete all tags from archive."
    )
    action_group.add_argument(
        "-e",
        "--pages",
        action=PageRangeAction,
        help="Extract a single page or : delimited range of pages by zero based index"
        "to --dest-path.",
    )
    action_group.add_argument(
        "-o", "--cover", action="store_true", help="Extract cover page(s)."
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
        help="Write comic metadata formats to archive cbt & cbr are always"
        " exported to cbz format. List of format keys.",
    )
    action_group.add_argument(
        "--rename",
        action="store_true",
        help="Rename the file with our preferred schema.",
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
    description = "Comic book archive read/write tool."
    formats = _create_format_help()
    epilog = (
        "Characters for --print-phases string:\n"
        "  v  Software version\n"
        "  t  File type\n"
        "  n  File names\n"
        "  s  Source metadata\n"
        "  p  Parsed metadata sources\n"
        "  l  Loaded metadata sources\n"
        "  c  Computed metadata sources\n"
        "  m  Final synthesized metadata.\n\n"
        "Complex --metadata example:\n"
        "  -m 'Character: anna,bea,carol, contributors: {inker: [Other Name],"
        " writer: [Other Name, Writer Name]},"
        " story_arcs: {Arc Name: 1, Other Arc Name: 5}'\n"
        "  -m '{publisher: My Press}'\n"
        "  -m 'Title: The Dark Freighter'\n"
        "\n"
        "  Metadata can be any tag from any of the supported metadata formats.\n\n"
        "Format keys for --ignore-read, --write, and --export:\n" + formats
    )
    parser = ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=RawDescriptionHelpFormatter,
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

    # Logleve
    if cns.quiet:
        cns.loglevel = INFO + cns.quiet * 10


def main(params=None):
    """Get CLI arguments and perform the operation on the archive."""
    cns = get_args(params)
    post_process_args(cns)
    args = Namespace(comicbox=cns)

    runner = Runner(args)
    try:
        runner.run()
    except HANDLED_EXCEPTIONS as exc:
        print(exc)  # noqa: T201
        sys.exit(1)
