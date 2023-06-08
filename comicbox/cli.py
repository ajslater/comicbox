"""Cli for comicbox."""
import sys
from argparse import Action, ArgumentParser, Namespace, RawDescriptionHelpFormatter
from collections.abc import Sequence

from comicbox.config import get_config
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.metadata.comet import CoMet
from comicbox.metadata.comicbookinfo import ComicBookInfo
from comicbox.metadata.comicinfoxml import ComicInfoXml
from comicbox.metadata.filename import FilenameMetadata
from comicbox.metadata.pdf import PDFParser
from comicbox.run import Runner

WRITE_KEY_MAPS = {
    "comet": CoMet,
    "comicbookinfo": ComicBookInfo,
    "comicinfoxml": ComicInfoXml,
    "filename": FilenameMetadata,
    "pdf": PDFParser,
}

READ_KEY_MAPS = {**WRITE_KEY_MAPS, "filename": FilenameMetadata}
HANDLED_EXCEPTIONS = (UnsupportedArchiveTypeError,)


class KeyValueDictAction(Action):
    """Parse comma delimited key value pairs key value."""

    def __call__(self, _parser, namespace, values, _option_string=None):
        """Parse comma delimited key value pairs."""
        if not values:
            return
        key, values_list = values.split("=")
        values_array = values_list.split(",")
        values_dict = {key: values_array}
        dest_dict = getattr(namespace, self.dest, {})
        if dest_dict is None:
            dest_dict = {}
        dest_dict.update(values_dict)
        setattr(namespace, self.dest, dest_dict)


class CSVAction(Action):
    """Parse comma deliminated sequences."""

    def __call__(self, _parser, namespace, values, _option_string=None):
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

    def __call__(self, _parser, namespace, values, _option_string=None):
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


def process_keys(config):
    """CLI config post processing."""
    map_keys(config, "read", "ignore_read", READ_KEY_MAPS, False)
    map_keys(config, "write", "write", WRITE_KEY_MAPS, True)


def get_args(params=None) -> Namespace:
    """Get arguments and options."""
    description = "Comic book archive read/write tool."
    epilog = (
        "Format keys:\n"
        f"    Comic Rack: {', '.join(sorted(ComicInfoXml.CONFIG_KEYS))}\n"
        f"    Comic Book Info: {', '.join(sorted(ComicBookInfo.CONFIG_KEYS))}\n"
        f"    CoMet: {', '.join(sorted(CoMet.CONFIG_KEYS))}\n"
        f"    Filename: {', '.join(sorted(FilenameMetadata.CONFIG_KEYS))}\n"
        f"    PDF: {', '.join(sorted(PDFParser.CONFIG_KEYS))}\n"
        "-w & -R can take comma separated lists of these keys."
    )
    parser = ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=RawDescriptionHelpFormatter,
    )
    # OPTIONS
    parser.add_argument(
        "-R",
        "--ignore-read",
        action=CSVAction,
        dest="ignore_read",
        help="Ignore reading metadata formats. List of format keys.",
    )
    parser.add_argument(
        "-d",
        "--dest-path",
        type=str,
        help="destination path for extracting pages and metadata.",
    )
    parser.add_argument(
        "--delete-orig",
        action="store_true",
        help="Delete the original file if it was converted to a cbz successfully.",
    )
    parser.add_argument(
        "--recurse",
        action="store_true",
        help="Perform selected actions recursively on a directory.",
    )
    parser.add_argument(
        "-g",
        "--config",
        action="store",
        type=str,
        help="Path to an alternate config file.",
    )
    parser.add_argument(
        "-y",
        "--dry-run",
        action="store_true",
        help="Do not write anything to the filesystem. Report on what would be done.",
    )
    parser.add_argument(
        "-m",
        "--metadata",
        action=KeyValueDictAction,
        help="Set metadata fields key=value,key=value",
    )

    ###########
    # ACTIONS #
    ###########
    parser.add_argument("-v", "--version", action="store_true", help="Display version.")
    parser.add_argument("-p", "--print", action="store_true", help="Print metadata")
    parser.add_argument(
        "-t",
        "--type",
        dest="file_type",
        action="store_true",
        help="Print archive file type",
    )
    parser.add_argument(
        "-n",
        "--index",
        dest="index",
        type=int,
        help="Extract a single page by zero based index.",
    )
    parser.add_argument(
        "-a",
        "--pages",
        action=PageRangeAction,
        help="Extract a single page or : delimited range of pages by zero based index.",
    )
    parser.add_argument(
        "-c", "--covers", action="store_true", help="Extract cover pages."
    )
    parser.add_argument(
        "-r", "--raw", action="store_true", help="Print raw metadata without parsing"
    )
    parser.add_argument(
        "-z", "--cbz", action="store_true", help="Export the archive to CBZ format."
    )
    parser.add_argument(
        "-i",
        "--import",
        action="store",
        dest="import_fn",
        help="Import metadata from an external file.",
    )
    parser.add_argument(
        "-e",
        "--export",
        action="store_true",
        help="Export metadata as external files in several formats.",
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Rename the file with our preferred schema.",
    )
    parser.add_argument(
        "--delete-tags", action="store_true", help="Delete all tags from archive."
    )
    parser.add_argument(
        "-w",
        "--write",
        action=CSVAction,
        help="Write comic metadata formats to archive. List of format keys.",
    )

    ###########
    # TARGETS #
    ###########
    parser.add_argument(
        "paths",
        metavar="path",
        type=str,
        help="Paths to comic archives or directories",
        nargs="*",
    )

    if params is not None:
        params = params[1:]
    cns = parser.parse_args(params)
    process_keys(cns)
    return Namespace(comicbox=cns)


def main(params=None):
    """Get CLI arguments and perform the operation on the archive."""
    args = get_args(params)
    config = get_config(args)

    runner = Runner(config)
    try:
        runner.run()
    except HANDLED_EXCEPTIONS as exc:
        print(exc)  # noqa: T201
        sys.exit(1)
