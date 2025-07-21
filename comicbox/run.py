"""Run comicbox on files."""

import os
from pathlib import Path

from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.config.frozenattrdict import FrozenAttrDict
from comicbox.logger import init_logging


class Runner:
    """Main runner."""

    _RECURSE_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".pdf"})

    def __init__(self, config):
        """Initialize actions and config."""
        self._config: FrozenAttrDict = FrozenAttrDict(get_config(config))
        init_logging(self._config.loglevel)

    def run_on_file(self, path):
        """Run operations on one file."""
        if path:
            path = Path(path)
            if not path.exists():
                logger.error(f"{path} does not exist.")
                return
            if path.is_dir() and self._config.recurse:
                self.recurse(path)
                return

        with Comicbox(path, config=self._config) as car:
            car.print_file_header()
            car.run()

    def recurse(self, path):
        """Perform operations recursively on files."""
        if not path.is_dir():
            logger.error(f"{path} is not a directory")
            return
        if not self._config.recurse:
            logger.warning(f"Recurse option not set. Ignoring directory {path}")
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
                    logger.exception(full_path)

    def run(self):
        """Run actions with config."""
        paths = self._config.paths
        for path in paths:
            self.run_on_file(path)
