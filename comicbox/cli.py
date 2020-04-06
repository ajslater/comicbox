#!/usr/bin/env python3
"""Cli for comicbox."""
import argparse

from pathlib import Path
from pprint import pprint

import pkg_resources

from .comic_archive import ComicArchive


PROGRAM_NAME = "comicbox"
VERSION = pkg_resources.get_distribution(PROGRAM_NAME).version


def get_args():
    """Get arguments and options."""
    description = "Comic book archive read/write tool."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "path", type=Path, help="Path to the comic archive",
    )
    parser.add_argument("-m", "--metadata", action="store_true", help="Print metadata")
    parser.add_argument("-v", "--version", action="store_true", help="Display version.")
    parser.add_argument(
        "-R",
        "--ignore-comicrack",
        action="store_false",
        dest="comicrack",
        default=True,
        help="Ignore ComicRack metadata if present.",
    )
    parser.add_argument(
        "-L",
        "--ignore-comiclover",
        action="store_false",
        dest="comiclover",
        default=True,
        help="Ignore ComicLover metadata if present.",
    )
    parser.add_argument(
        "-C",
        "--ignore-comet",
        action="store_false",
        dest="comet",
        default=True,
        help="Ignore CoMet metadata if present.",
    )
    parser.add_argument(
        "-F",
        "--ignore-filename",
        action="store_false",
        dest="filename",
        default=True,
        help="Ignore filename metadata.",
    )
    parser.add_argument(
        "-f",
        "--from",
        dest="index_from",
        type=int,
        help="Extract pages from the specified index forward.",
    )
    parser.add_argument(
        "-p",
        "--root_path",
        default=".",
        type=Path,
        help="root path to extracting pages and metadata.",
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
        "--delete-rar",
        action="store_true",
        help="Delete the original rar file if the zip is exported sucessfully.",
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
        help="Rename the file with our preferred schema." "",
    )
    parser.add_argument(
        "--delete", action="store_true", help="Delete all tags from archive."
    )

    return parser.parse_args()


def main():
    """Get CLI arguments and perform the operation on the archive."""
    args = get_args()
    if args.version:
        print(VERSION)
        return
    if not args.path.is_file():
        print("{args.path} is not a file.")

    car = ComicArchive(args.path, settings=args)
    if args.raw:
        for key, val in car.raw.items():
            print("-" * 10, key, "-" * 10)
            if isinstance(val, bytes):
                val = val.decode()
            print(val)
    elif args.metadata:
        pprint(car.get_metadata())
    elif args.covers:
        car.extract_covers(args.root_path)
    elif args.index_from:
        car.extract_pages(args.index_from, args.root_path)
    elif args.export:
        car.export_files()
    elif args.delete:
        car.delete_tags()
    elif args.cbz:
        new_path = car.recompress()
        print(f"converted to: {new_path}")
        if args.delete_rar:
            if new_path.is_file():
                args.path.unlink()
                print(f"removed: {args.path}")
    elif args.import_fn:
        car.import_file(args.import_fn)
    elif args.rename:
        car.rename_file()
    else:
        print("Nothing to do.")


if __name__ == "__main__":
    main()
