"""Run comicbox on files."""
import os
import sys

from logging import getLogger
from pathlib import Path
from pprint import pprint

from comicbox.comic_archive import ComicArchive
from comicbox.version import VERSION


LOG = getLogger(__name__)


class Runner:
    """Main runner."""

    SUFFIXES = frozenset((".cbz", ".cbr"))

    def __init__(self, config):
        """Initialize actions and config."""
        self.config = config
        self.noop = True

    def run_on_file(self, path):
        """Run operations on one file."""
        if path.is_dir() and self.config.recurse:
            self.recurse(path)

        if not path.is_file():
            print(f"{path} is not a file.")
            return

        car = ComicArchive(path, config=self.config)
        if self.config.raw:
            car.print_raw()
            self.noop = False
        if self.config.print:
            pprint(car.get_metadata())
            self.noop = False
        if self.config.covers:
            car.extract_cover_as(self.config.dest_path)
            self.noop = False
        if self.config.index_from:
            car.extract_pages(self.config.index_from, self.config.dest_path)
            self.noop = False
        if self.config.export:
            car.export_files()
            self.noop = False
        if self.config.cbz or self.config.delete_tags:
            car.recompress()
            self.noop = False
        if self.config.import_fn:
            car.import_file(self.config.import_fn)
            self.noop = False
        if self.config.rename:
            car.rename_file()
            self.noop = False

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
                full_path = root_path / dirname
                self.recurse(full_path)
            for filename in sorted(filenames):
                if Path(filename).suffix.lower() not in self.SUFFIXES:
                    continue
                full_path = root_path / filename
                try:
                    self.run_on_file(full_path)
                except Exception as exc:
                    LOG.error(f"{full_path}: {type(exc).__name__} {exc}")

    def run(self):
        """Run actions with config."""
        if self.config.version:
            print(VERSION)
        if not self.config.paths:
            if self.config.version:
                return
            else:
                print("the following arguments are required: paths")
                sys.exit(1)

        for path in self.config.paths:
            self.run_on_file(Path(path))

        if self.noop:
            print("No action performed")
