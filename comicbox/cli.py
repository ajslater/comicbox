#!/usr/bin/env python3
"""Cli for comicbox."""
import argparse

from pathlib import Path

from comicbox.config import get_config
from comicbox.run import Runner


def get_args():
    """Get arguments and options."""
    description = "Comic book archive read/write tool."
    parser = argparse.ArgumentParser(description=description)
    # OPTIONS
    parser.add_argument(
        "-R",
        "--ignore-comicrack",
        action="store_false",
        dest="comicrack",
        help="Ignore ComicRack metadata if present.",
    )
    parser.add_argument(
        "-L",
        "--ignore-comiclover",
        action="store_false",
        dest="comiclover",
        help="Ignore ComicLover metadata if present.",
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
        "-d",
        "--dest_path",
        type=Path,
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
        help="Perform seletced actions recursively on a directory.",
    )
    parser.add_argument(
        "-g",
        "--config",
        action="store",
        type=Path,
        help="Path to an alternate config file.",
    )

    ###########
    # ACTIONS #
    ###########
    parser.add_argument("-v", "--version", action="store_true", help="Display version.")
    parser.add_argument("-p", "--metadata", action="store_true", help="Print metadata")
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
        "--delete_tags", action="store_true", help="Delete all tags from archive."
    )

    ###########
    # TARGETS #
    ###########
    parser.add_argument(
        "paths", type=Path, help="Path to comic archives or directories", nargs="*"
    )

    return parser.parse_args()


def main():
    """Get CLI arguments and perform the operation on the archive."""
    args = get_args()
    config = get_config(args)
    runner = Runner(args, config)
    runner.run()


if __name__ == "__main__":
    main()
