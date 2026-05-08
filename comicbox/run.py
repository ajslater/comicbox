"""Run comicbox on files."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.logger import init_logging
from comicbox.online import outcome_stats

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator

    from comicbox.config.settings import ComicboxSettings


class Runner:
    """Main runner."""

    _RECURSE_SUFFIXES = frozenset({".cbz", ".cbr", ".cbt", ".pdf"})

    def __init__(self, config: Namespace) -> None:
        """Initialize actions and config."""
        self._config: ComicboxSettings = get_config(config)
        init_logging(self._config.loglevel)

    def _iter_recurse(self, path: Path) -> Iterator[Path]:
        for full_path in sorted(path.rglob("*")):
            if not full_path.is_file():
                continue
            if full_path.suffix.lower() not in self._RECURSE_SUFFIXES:
                continue
            yield full_path

    def _expand_paths(self) -> list[Path]:
        """Flatten config.paths, expanding directories under --recurse."""
        out: list[Path] = []
        for raw in self._config.paths or ():
            if not raw:
                continue
            path = Path(raw)
            if not path.exists():
                logger.error(f"{path} does not exist.")
                continue
            if path.is_dir():
                if self._config.recurse:
                    out.extend(self._iter_recurse(path))
                else:
                    logger.warning(f"Recurse option not set. Ignoring directory {path}")
                continue
            out.append(path)
        return out

    def _run_one(self, path: Path) -> None:
        """Process a single file, swallowing exceptions for batch resilience."""
        try:
            with Comicbox(path, config=self._config) as car:
                car.print_file_header()
                car.run()
        except Exception:
            logger.exception(path)

    def run_on_file(self, path: Path | str | None) -> None:
        """Run operations on one file (single-file CLI invocation)."""
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

    def recurse(self, path: Path) -> None:
        """Perform operations recursively on files (single-threaded)."""
        if not path.is_dir():
            logger.error(f"{path} is not a directory")
            return
        if not self._config.recurse:
            logger.warning(f"Recurse option not set. Ignoring directory {path}")
            return

        for full_path in self._iter_recurse(path):
            try:
                self.run_on_file(full_path)
            except Exception:
                logger.exception(full_path)

    def _run_parallel(self, paths: list[Path], jobs: int) -> None:
        """
        Run files via a thread pool. Online prompts serialize via a class-level lock.

        Threads (not processes): online lookup is I/O-bound and the
        upstream rate limiters (mokkari/simyan via pyrate_limiter) are
        process-wide and thread-safe, so workers share the rate budget
        without coordination from us.
        """
        logger.info(f"Running {len(paths)} files with {jobs} workers")
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(self._run_one, p): p for p in paths}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.exception(path)

    def run(self) -> None:
        """Run actions with config."""
        outcome_stats.reset()
        try:
            self._run_inner()
        finally:
            for line in outcome_stats.summary_lines():
                logger.info(line)

    def _run_inner(self) -> None:
        """Dispatch to serial or parallel processing based on `--jobs`."""
        jobs = max(1, self._config.jobs)
        # Fast path: single file or no parallelism. Preserves the original
        # one-call-per-path control flow including its recurse handling.
        if jobs <= 1:
            for raw in self._config.paths or ():
                self.run_on_file(raw)
            return

        # Parallel path: expand directories first so the thread pool sees
        # a flat path list.
        paths = self._expand_paths()
        if not paths:
            logger.warning("No files to process")
            return
        if len(paths) == 1:
            self._run_one(paths[0])
            return
        self._run_parallel(paths, jobs)
