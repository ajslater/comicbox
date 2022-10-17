#!/usr/bin/env python3
"""Cli for comicbox."""
from argparse import Action, ArgumentParser, Namespace

from comicbox.config import get_config
from comicbox.run import Runner


class KeyValueDictAction(Action):
    """Parse comma deliminted key value pairs key value."""

    def __call__(self, parser, namespace, values, _option_string=None):
        """Parse comma deliminated key value pairs."""
        if values:
            values = dict(item.split("=") for item in values.split(","))
        else:
            values = {}
        setattr(namespace, self.dest, values)


def get_args(params=None) -> Namespace:
    """Get arguments and options."""
    description = "Comic book archive read/write tool."
    parser = ArgumentParser(description=description)
    # OPTIONS
    parser.add_argument(
        "-R",
        "--ignore-cix",
        action="store_false",
        dest="comicinfo",
        help="Ignore ComicRack ComicInfo.xml metadata if present.",
    )
    parser.add_argument(
        "-L",
        "--ignore-cbi",
        action="store_false",
        dest="comicbookinfo",
        help="Ignore ComicLover ComicBookInfo metadata if present.",
    )
    parser.add_argument(
        "-C",
        "--ignore-comet",
        action="store_false",
        dest="comet",
        help="Ignore CoMet metadata if present.",
    )
    parser.add_argument(
        "-F",
        "--ignore-filename",
        action="store_false",
        dest="filename",
        help="Ignore filename metadata.",
    )
    parser.add_argument(
        "-M",
        "--no-metadata",
        action="store_false",
        help="Do not read any comic metadata.",
    )
    parser.add_argument(
        "-d",
        "--dest-path",
        type=str,
        help="destination path for extracting pages and metadata.",
    )
    parser.add_argument(
        "--delete-rar",
        action="store_true",
        help="Delete the original rar file if the zip is exported successfully.",
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
        "-f",
        "--from",
        dest="index_from",
        type=int,
        help="Extract pages from the specified index forward.",
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
    return Namespace(comicbox=cns)


def main(params=None):
    """Get CLI arguments and perform the operation on the archive."""
    args = get_args(params)
    config = get_config(args)

    runner = Runner(config)
    runner.run()


if __name__ == "__main__":
    main()
