"""Run comicbox on files."""
import os
import sys

from pathlib import Path
from pprint import pprint

from comicbox.comic_archive import ComicArchive
from comicbox.version import VERSION


class Runner:
    """Main runner."""

    SUFFIXES = frozenset((".cbz", ".cbr"))

    def __init__(self, args, config):
        """Initialize actions and config."""
        self.args = args
        self.config = config

    def run_on_file(self, path):
        """Run operations on one file."""
        if path.is_dir() and self.config.recurse:
            self.recurse(path)

        if not path.is_file():
            print(f"{path} is not a file.")
            return

        car = ComicArchive(path, config=self.config)
        if self.args.raw:
            car.print_raw()
        if self.args.metadata:
            pprint(car.get_metadata())
        if self.args.covers:
            car.extract_cover_as(self.config.dest_path)
        if self.args.index_from:
            car.extract_pages(self.args.index_from, self.config.dest_path)
        if self.args.export:
            car.export_files()
        if self.args.cbz or self.args.delete_tags:
            car.recompress()
        if self.args.import_fn:
            car.import_file(self.args.import_fn)
        if self.args.rename:
            car.rename_file()

    def recurse(self, path):
        """Perform operations recursively on files."""
        if not path.is_dir():
            print(f"{path} is not a directory")
            sys.exit(1)
        if not self.config.recurse:
            print(f"Recurse option not set. Ignoring directory {path}")
            return

        for root, dirnames, filenames in os.walk(path):
            root_path = Path(root)
            for dirname in dirnames:
                self.recurse(dirname)
            for filename in sorted(filenames):
                if Path(filename).suffix.lower() not in self.SUFFIXES:
                    continue
                full_path = root_path / filename
                self.run_on_file(full_path)

    def run(self):
        """Run actions with config."""
        if self.args.version:
            print(VERSION)
        if not self.args.paths:
            if self.args.version:
                return
            else:
                print("the following arguments are required: paths")
                sys.exit(1)

        for path in self.args.paths:
            self.run_on_file(path)
