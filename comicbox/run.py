"""Run comicbox on files."""

import os
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

from comicbox.box.comic import Comicbox
from comicbox.config import get_config

if TYPE_CHECKING:
    from confuse import AttrDict

LOG = getLogger(__name__)


class Runner:
    """Main runner."""

    _RECURSE_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".pdf"})

    def __init__(self, config):
        """Initialize actions and config."""
        self.config: AttrDict = get_config(config)

    def run_on_file(self, path):
        """Run operations on one file."""
        if path:
            path = Path(path)
            if not path.exists():
                LOG.error(f"{path} does not exist.")
                return
            if path.is_dir() and self.config.recurse:
                self.recurse(path)
                return

        with Comicbox(path, config=self.config) as car:
            car.print_file_header()
            car.run()

    def recurse(self, path):
        """Perform operations recursively on files."""
        if not path.is_dir():
            LOG.error(f"{path} is not a directory")
            return
        if not self.config.recurse:
            LOG.warning(f"Recurse option not set. Ignoring directory {path}")
            return

        for root, dirnames, filenames in os.walk(path):
            root_path = Path(root)
            for dirname in dirnames:
                full_path = root_path / dirname
                self.recurse(full_path)
            for filename in sorted(filenames):
                path = Path(str(filename))
                if path.suffix.lower() not in self._RECURSE_SUFFIXES:
                    continue
                full_path = root_path / path
                try:
                    self.run_on_file(full_path)
                except Exception:
                    LOG.exception(full_path)

    def run(self):
        """Run actions with config."""
        paths = self.config.paths
        for path in paths:
            self.run_on_file(path)
