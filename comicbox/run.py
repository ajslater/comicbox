"""Run comicbox on files."""

from argparse import Namespace
from pathlib import Path
from typing import Any

from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.config.frozenattrdict import FrozenAttrDict
from comicbox.logger import init_logging


class Runner:
    """Main runner."""

    _RECURSE_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".pdf"})

    def __init__(self: Any, config: Namespace) -> None:
        """Initialize actions and config."""
        self._config: FrozenAttrDict = FrozenAttrDict(get_config(config))
        init_logging(self._config.loglevel)

    def run_on_file(self: Any, path: Path | str) -> None:
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

    def recurse(self: Any, path: Path) -> None:
        """Perform operations recursively on files."""
        if not path.is_dir():
            logger.error(f"{path} is not a directory")
            return
        if not self._config.recurse:
            logger.warning(f"Recurse option not set. Ignoring directory {path}")
            return

        for full_path in sorted(path.rglob("*")):
            if not full_path.is_file():
                continue
            if full_path.suffix.lower() not in self._RECURSE_SUFFIXES:
                continue
            try:
                self.run_on_file(full_path)
            except Exception:
                logger.exception(full_path)

    def run(self: Any) -> None:
        """Run actions with config."""
        paths = self._config.paths
        for path in paths:
            self.run_on_file(path)
