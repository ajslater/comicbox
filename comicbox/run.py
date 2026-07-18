"""Run comicbox on files."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.auto_engage import resolve_auto_engaged_budget
from comicbox.formats.base.online.rate_limits import METRON_DEFAULT_PER_MINUTE
from comicbox.logger import init_logging

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
        init_logging(self._config.general.loglevel)

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
                if self._config.general.recurse:
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
            if path.is_dir() and self._config.general.recurse:
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
        if not self._config.general.recurse:
            logger.warning(f"Recurse option not set. Ignoring directory {path}")
            return

        for full_path in self._iter_recurse(path):
            try:
                self.run_on_file(full_path)
            except Exception:
                logger.exception(full_path)

    def _metron_is_active(self) -> bool:
        """Best-effort check: could this run actually hit Metron via mokkari."""
        online = self._config.online
        if not online.lookup.enabled:
            return False
        sources = online.lookup.sources
        if sources is not None and "metron" not in sources:
            return False
        creds = online.auth.sources.get("metron")
        return bool(creds and creds.user and creds.password)

    def _run_parallel(self, paths: list[Path], jobs: int) -> None:
        """
        Run files via a thread pool. Online prompts serialize via a class-level lock.

        Threads (not processes): online lookup is I/O-bound, and
        `MetronOnlineSource` shares one mokkari `Session` per credential
        set (comicbox/formats/metron_api/online_source.py) so every worker
        here sees the same `rate_limit_status` mokkari reads off Metron's
        response headers, instead of each file's source starting cold.

        That check is advisory, not a hard gate — mokkari can't serialize
        "check the last known headers" with "send the request" across
        threads, so a burst of workers can each pass the check before any
        of their responses land. mokkari's own guidance for a shared
        Session is to cap the pool at the burst limit rather than rely on
        the header check alone, so we do that here when Metron is an
        active source for this run.
        """
        if self._metron_is_active():
            jobs = min(jobs, METRON_DEFAULT_PER_MINUTE)
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

    def _maybe_auto_engage_api_budget(self, batch_size: int) -> None:
        """
        Auto-engage `api_budget=fast` for large unattended runs.

        Mutates `self._config` in place (well, replaces via
        `dataclasses.replace`) so downstream Comicbox instances see the
        engaged budget. No-op when:

        - `online` isn't enabled (the only consumer of api_budget)
        - batch is small (single-fixture interactive use)
        - user pinned the global budget or any per-source budget

        See `comicbox.formats.base.online.auto_engage` for the trigger semantics.
        """
        if not self._config.online.lookup.enabled:
            return
        engaged = resolve_auto_engaged_budget(self._config.online, batch_size)
        if engaged is self._config.online:
            return
        self._config = replace(self._config, online=engaged)

    def _run_inner(self) -> None:
        """Dispatch to serial or parallel processing based on `--jobs`."""
        jobs = max(1, self._config.general.jobs)
        # Fast path: single file or no parallelism. Preserves the original
        # one-call-per-path control flow including its recurse handling.
        if jobs <= 1:
            # Expand paths up-front so we know the batch size for
            # auto-engagement. Reuse `_expand_paths` for parity with the
            # parallel branch; serial dispatch still calls `run_on_file`
            # which handles directory expansion under `--recurse`, so the
            # actual processing is unchanged.
            paths = self._expand_paths()
            self._maybe_auto_engage_api_budget(len(paths))
            for raw in self._config.paths or ():
                self.run_on_file(raw)
            return

        # Parallel path: expand directories first so the thread pool sees
        # a flat path list.
        paths = self._expand_paths()
        if not paths:
            logger.warning("No files to process")
            return
        self._maybe_auto_engage_api_budget(len(paths))
        if len(paths) == 1:
            self._run_one(paths[0])
            return
        self._run_parallel(paths, jobs)
