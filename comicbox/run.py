"""Run comicbox on files."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import OnlineLookupAbortedError, UnsupportedArchiveTypeError
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.auto_engage import resolve_auto_engaged_budget
from comicbox.formats.base.online.rate_limits import METRON_DEFAULT_PER_MINUTE
from comicbox.formats.base.online.series_cache import (
    SeriesCache,
    filename_series_fingerprint,
)
from comicbox.logger import init_logging

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator, Mapping

    from comicbox.config.settings import ComicboxSettings

#: Expected per-file failures: the path simply isn't an archive we can
#: open. A traceback tells the user nothing the message doesn't, so these
#: log one line. Anything else is a bug and earns the stack.
_EXPECTED_FILE_ERRORS = (UnsupportedArchiveTypeError,)


class Runner:
    """Main runner."""

    # Derived from the file-type enum so a newly supported archive can't be
    # left out of a recursive walk. Hardcoding the set is what dropped .cb7.
    _RECURSE_SUFFIXES = frozenset(
        {"." + file_type.value.lower() for file_type in FileTypeEnum}
    )

    def __init__(self, config: Namespace | Mapping | ComicboxSettings | None) -> None:
        """Initialize actions and config."""
        self._config: ComicboxSettings = get_config(config)
        #: Files this run couldn't process. Batch dispatch logs a failure
        #: and keeps going, so this is the only record that anything went
        #: wrong; `comicbox.cli.main` exits non-zero when it's non-empty.
        self.failure_count = 0
        self._failure_lock = threading.Lock()
        #: Batch-wide series cache for online tagging (series-first
        #: batching, plan §3.10). `OnlineSession` has always had one; the
        #: CLI did not, so `comicbox --online` re-ran the full candidate
        #: search for every issue of a series even inside one `-j N`
        #: batch. A plain dict guarded by a lock: the pool's workers all
        #: read and write it, and `_maybe_populate_series_cache` needs
        #: `in` / `__setitem__` to stay consistent between them.
        self._series_cache = SeriesCache()
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

    def _record_failure(self) -> None:
        """Count one failed file. Called from pool workers, so locked."""
        with self._failure_lock:
            self.failure_count += 1

    def _run_one(self, path: Path | str | None) -> None:
        """
        Process one batch element, swallowing exceptions for batch resilience.

        The single guard every batch dispatch shares — serial, recursive
        and threaded — so one unreadable comic costs its own file and
        nothing more, whatever `-j` says. It used to wrap only the thread
        pool, which made the same corrupt file a logged error under
        `-j 2` and a fatal one under `-j 1`.

        `run_on_file` stays unguarded on purpose: a caller asking about
        one file wants to hear that it failed.

        Abort is the one exception that isn't about this file: the user
        answered "abort" at a prompt (or a caller cancelled a retry
        sleep), which is a decision about the run. Swallowing it here
        turned it into "skip one comic and keep prompting for the rest."
        """
        try:
            self.run_on_file(path)
        except OnlineLookupAbortedError:
            raise
        except _EXPECTED_FILE_ERRORS as exc:
            self._record_failure()
            logger.error(exc)
        except Exception:
            self._record_failure()
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
            if self._config.online.lookup.enabled:
                car.set_series_cache(self._series_cache)
            car.print_file_header()
            car.run()

    def _order_for_series_batching(self, paths: list[Path]) -> list[Path]:
        """
        Cluster same-series files together so the series cache can hit.

        Mirrors `OnlineSession.tag_many`: the first issue of each cluster
        pays for the cold-path search and resolves the volume id; the
        rest of the cluster reads it back and goes straight to the
        volume-scoped issue lookup. Sorting by fingerprint makes the
        cluster order deterministic, so re-runs produce the same
        cache-key sequence.

        Only reorders when online lookup is on — for every other
        operation the input order is the user's and we leave it alone.
        """
        if not self._config.online.lookup.enabled:
            return paths
        return sorted(paths, key=filename_series_fingerprint)

    def recurse(self, path: Path) -> None:
        """Perform operations recursively on files (single-threaded)."""
        if not path.is_dir():
            logger.error(f"{path} is not a directory")
            return
        if not self._config.general.recurse:
            logger.warning(f"Recurse option not set. Ignoring directory {path}")
            return

        # `_run_one` guards each file and lets an abort through, which
        # ends the walk: the remaining files are not ours to keep
        # processing.
        for full_path in self._iter_recurse(path):
            self._run_one(full_path)

    def _metron_is_active(self) -> bool:
        """Best-effort check: could this run actually hit Metron via mokkari."""
        online = self._config.online
        if not online.lookup.enabled:
            return False
        # Falsy-collapse matches _build_active_online_sources: both None and
        # the empty ALL_SOURCES sentinel () mean "every configured source".
        sources = online.lookup.sources
        if sources and "metron" not in sources:
            return False
        creds = online.auth.sources.get("metron")
        return bool(creds and (creds.key or (creds.user and creds.password)))

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
        if self._metron_is_active() and jobs > METRON_DEFAULT_PER_MINUTE:
            logger.info(
                f"Capping --jobs {jobs} to {METRON_DEFAULT_PER_MINUTE} "
                "(Metron's burst limit; the shared-session rate-limit check "
                "is advisory under concurrent threads)"
            )
            jobs = METRON_DEFAULT_PER_MINUTE
        logger.info(f"Running {len(paths)} files with {jobs} workers")
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(self._run_one, p): p for p in paths}
            try:
                for future in as_completed(futures):
                    path = futures[future]
                    try:
                        future.result()
                    except OnlineLookupAbortedError:
                        raise
                    except Exception:
                        logger.exception(path)
            except OnlineLookupAbortedError:
                # Drop every file still queued so the abort actually ends
                # the batch. Workers already in flight can't be
                # interrupted from here -- the pool joins them on the way
                # out -- but no further file is started.
                for pending in futures:
                    pending.cancel()
                raise

    def run(self) -> None:
        """Run actions with config."""
        outcome_stats.reset()
        self.failure_count = 0
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
            if self._config.online.lookup.enabled:
                # Online serial runs dispatch over the EXPANDED, clustered
                # list so the series cache sees same-series files
                # back-to-back. Offline runs keep the original
                # one-call-per-configured-path control flow, which is what
                # `--recurse` directory handling is written against.
                for path in self._order_for_series_batching(paths):
                    self._run_one(path)
                return
            for raw in self._config.paths or ():
                self._run_one(raw)
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
        self._run_parallel(self._order_for_series_batching(paths), jobs)
