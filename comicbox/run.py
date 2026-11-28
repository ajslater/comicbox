"""Run comicbox on files."""

from __future__ import annotations

import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from comicbox.box import Comicbox
from comicbox.box.pages.extract import CoverDestinations
from comicbox.config import get_config
from comicbox.enums.comicbox import FileTypeEnum
from comicbox.exceptions import (
    ComicNotFoundError,
    DestinationOccupiedError,
    DuplicateMemberError,
    ExportError,
    ImportFileError,
    OnlineLookupAbortedError,
    ReadOnlyComicError,
    UnparsedTagFileError,
    UnsafePdfAttachmentError,
    UnsupportedArchiveTypeError,
    UnwritableFormatError,
    UsageError,
    ValidationFailedError,
)
from comicbox.formats.base.online import outcome_stats, retry
from comicbox.formats.base.online.auto_engage import resolve_auto_engaged_budget
from comicbox.formats.base.online.series_cache import (
    SeriesCache,
    filename_series_fingerprint,
)
from comicbox.formats.base.online.session_state import OnlineSessionState
from comicbox.logger import init_logging
from comicbox.version import set_user_agent_context

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterable, Iterator, Mapping

    from comicbox.config.settings import ComicboxSettings

#: Expected per-file failures, refusals comicbox makes on purpose: the path
#: names nothing or isn't an archive we can open, a keep write refused a
#: comic whose tag file did not parse, a write or rename would land on a
#: file already there, a PDF write would harm another attachment, -w names
#: no format the archive can hold, the comic is read-only, a conversion
#: would lose one of two members of one name, an export or extraction
#: failed, or the comic's metadata failed --validate. A traceback tells the
#: user nothing the message doesn't, so these log one line. Anything else is
#: a bug and earns the stack.
_EXPECTED_FILE_ERRORS = (
    ComicNotFoundError,
    UnsupportedArchiveTypeError,
    UnparsedTagFileError,
    DestinationOccupiedError,
    UnsafePdfAttachmentError,
    UnwritableFormatError,
    ReadOnlyComicError,
    DuplicateMemberError,
    ExportError,
    ImportFileError,
    ValidationFailedError,
)

#: The online sources that hold process-wide clients to release at the
#: end of a run. Named, not imported: see `_close_shared_online_sessions`.
_ONLINE_SOURCE_MODULES = (
    "comicbox.formats.metron_api.online_source",
    "comicbox.formats.comicvine_api.online_source",
    "comicbox.formats.versedb_api.online_source",
)


def _leaders_first(clustered: list[Path]) -> list[Path]:
    """
    Reorder a fingerprint-sorted list to one file per series, then the rest.

    Preserves each cluster's internal order and the deterministic cluster
    order the sort produced, so a re-run still walks the same sequence.
    """
    groups: dict[str, list[Path]] = {}
    for path in clustered:
        groups.setdefault(filename_series_fingerprint(path), []).append(path)
    leaders = [group[0] for group in groups.values()]
    followers = [path for group in groups.values() for path in group[1:]]
    return leaders + followers


def _close_shared_online_sessions() -> None:
    """
    Release the connections and handles a run opened, if it opened any.

    Read out of ``sys.modules`` rather than imported: an offline run
    never loads the online packages, and importing one here just to call
    a no-op would put mokkari's and simyan's import cost back on every
    run.
    """
    for name in _ONLINE_SOURCE_MODULES:
        module = sys.modules.get(name)
        if module is not None:
            module.close_shared_sessions()


# Derived from the file-type enum so a newly supported archive can't be
# left out of a recursive walk. Hardcoding the set is what dropped .cb7.
_RECURSE_SUFFIXES = frozenset(
    {"." + file_type.value.lower() for file_type in FileTypeEnum}
)


def iter_recurse(path: Path) -> Iterator[Path]:
    """Yield every comic archive under a directory, in sorted order."""
    for full_path in sorted(path.rglob("*")):
        if not full_path.is_file():
            continue
        if full_path.suffix.lower() not in _RECURSE_SUFFIXES:
            continue
        yield full_path


@dataclass(frozen=True, slots=True)
class _SameFiles:
    """
    The paths of a run that name a file the run reaches by another path too.

    ``process_as`` maps the one path of each such file that is processed
    to its real path: a path that is not a symbolic link, or else the
    link's target. ``same_as`` maps every other path to that real path.
    """

    process_as: Mapping[Path, Path] = field(default_factory=dict)
    same_as: Mapping[Path, Path] = field(default_factory=dict)


def _same_files(paths: Iterable[Path]) -> _SameFiles:
    """
    Group a run's paths by the file they name.

    With -r over a directory holding real.cbt and link.cbt -> real.cbt,
    both were converted, and --delete-orig deleted the link and kept the
    file. A file the run reaches by one path is left as it is, a symbolic
    link included, and so is one path given twice.
    """
    from comicbox.box.archive.write import file_key

    groups: dict[Any, list[Path]] = {}
    for path in dict.fromkeys(paths):
        groups.setdefault(file_key(path), []).append(path)
    process_as: dict[Path, Path] = {}
    same_as: dict[Path, Path] = {}
    for members in groups.values():
        if len(members) < 2:  # noqa: PLR2004
            continue
        chosen = next((path for path in members if not path.is_symlink()), members[0])
        real = chosen.resolve() if chosen.is_symlink() else chosen
        process_as[chosen] = real
        same_as.update({path: real for path in members if path != chosen})
    return _SameFiles(process_as, same_as)


class Runner:
    """Main runner."""

    def __init__(self, config: Namespace | Mapping | ComicboxSettings | None) -> None:
        """Initialize actions and config."""
        self._config: ComicboxSettings = get_config(config)
        #: Files this run couldn't process. Batch dispatch logs a failure
        #: and keeps going, so this is the only record that anything went
        #: wrong; `comicbox.cli.main` exits non-zero when it's non-empty.
        self.failure_count = 0
        self._failure_lock = threading.Lock()
        #: A file the run reaches by several paths, processed once.
        self._same_files = _SameFiles()
        #: The cover files this run wrote: a second comic's is refused.
        self._cover_destinations = CoverDestinations()
        #: Batch-wide series cache for online tagging (series-first
        #: batching, plan §3.10). `OnlineSession` has always had one; the
        #: CLI did not, so `comicbox --online` re-ran the full candidate
        #: search for every issue of a series even inside one `-j N`
        #: batch. A plain dict guarded by a lock: the pool's workers all
        #: read and write it, and `_maybe_populate_series_cache` needs
        #: `in` / `__setitem__` to stay consistent between them.
        self._series_cache = SeriesCache()
        #: Batch-wide owner of the two mutable lookup settings. Seeded from
        #: the config-resolved values; a `set_policy` / `set_prompts`
        #: answered at any file's prompt applies to the rest of the batch.
        #: Built here rather than after `_maybe_auto_engage_effort`
        #: because that only rewrites per-source effort, never match or
        #: prompts — and `run_on_file` is a public entry point that never
        #: goes through `run()`.
        self._online_state = OnlineSessionState.from_lookup(self._config.online.lookup)
        #: How many comics of each series the batch holds, by filename
        #: fingerprint. Filled once the paths are expanded; empty for
        #: `run_on_file`, which is one file and clusters nothing.
        self._series_cluster_sizes: Counter[str] = Counter()
        init_logging(self._config.general.loglevel)

    @staticmethod
    def _iter_recurse(path: Path) -> Iterator[Path]:
        return iter_recurse(path)

    def _expand_paths(self) -> list[Path]:
        """
        Flatten config.paths, expanding directories under --recurse.

        A path that names nothing is kept, so its dispatch reports it and
        counts it as failed once, whichever branch the run takes.
        """
        out: list[Path] = []
        for raw in self._config.paths or ():
            if not raw:
                continue
            path = Path(raw)
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
            # A path that names nothing gets as far as `Comicbox`, which
            # raises `ComicNotFoundError`: a failed file, not a skipped one.
            path = Path(path)
            if path.is_dir() and self._config.general.recurse:
                self.recurse(path)
                return
            if real := self._same_files.same_as.get(path):
                logger.info(f"{path}: same file as {real}")
                return
            path = self._same_files.process_as.get(path, path)

        with Comicbox(path, config=self._config) as car:
            if self._config.convert.extract_covers:
                car.set_cover_destinations(self._cover_destinations)
            if self._config.online.lookup.enabled:
                car.set_series_cache(self._series_cache)
                car.set_online_session_state(self._online_state)
                car.set_series_cluster_size(self._cluster_size_for(path))
            car.print_file_header()
            car.run()

    def _cluster_size_for(self, path: Path | str | None) -> int:
        """
        Return how many comics of this file's series the batch holds.

        1 for a pathless box (metadata read from stdin) and for anything
        the batch never counted, which is the honest answer: a lone comic
        has no cluster to amortize a prefetch over.
        """
        if not path:
            return 1
        fingerprint = filename_series_fingerprint(Path(path))
        return self._series_cluster_sizes.get(fingerprint, 1)

    def _note_series_clusters(self, paths: list[Path]) -> None:
        """
        Count the batch's series, so a source can prefetch the big ones.

        Filename-derived, like the batching order itself: it has to be
        known before any archive is opened, and it only has to be good
        enough to answer "is listing this whole series cheaper than one
        lookup per comic".
        """
        if not self._config.online.lookup.enabled:
            return
        self._series_cluster_sizes = Counter(
            filename_series_fingerprint(path) for path in paths
        )

    def _order_for_series_batching(
        self, paths: list[Path], jobs: int = 1
    ) -> list[Path]:
        """
        Order files so the series cache hits instead of being raced.

        Serially, clustering is enough: the first issue of each cluster
        pays for the cold-path search and resolves the volume id, and the
        rest read it back and go straight to the volume-scoped issue
        lookup. Sorting by fingerprint makes the cluster order
        deterministic, so re-runs produce the same cache-key sequence.

        In parallel, clustering alone is actively counterproductive. A
        pool of N takes the first N paths at once — all the same series —
        so all N miss the cache and the batching saves nothing for
        exactly the files it exists for. (`SeriesCache`'s single-flight
        leadership makes that safe, but the followers still sit and wait.)
        So with a pool, LEADERS GO FIRST: one file from each cluster, then
        the remainder still clustered. The pool's first N tasks are then N
        different series, each resolving its own, and the followers arrive
        to a warm cache instead of a queue.

        Only reorders when online lookup is on — for every other
        operation the input order is the user's and we leave it alone.
        """
        if not self._config.online.lookup.enabled:
            return paths
        clustered = sorted(paths, key=filename_series_fingerprint)
        if jobs <= 1:
            return clustered
        return _leaders_first(clustered)

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

    def _run_parallel(self, paths: list[Path], jobs: int) -> None:
        """
        Run files via a thread pool. Online prompts serialize via a class-level lock.

        Threads (not processes): online lookup is I/O-bound, and the
        online sources share process-wide state per credential set —
        one mokkari `Session`, whose `rate_limiter` hook is this
        credential set's `RateGate`
        (comicbox/formats/base/online/rate_gate.py), and every worker's
        requests are admitted through it. Since mokkari 4.8.0 that one
        Session also pools its HTTP connections (`HTTP_POOL_MAXSIZE` is
        32): above 32 workers the extra threads just fall back to a
        connection apiece with a urllib3 warning, and the gate bounds
        in-flight sends regardless.

        `jobs` is no longer clamped to Metron's burst limit. That clamp
        bounded the wrong unit: workers, not requests. A pool of 20 still
        sent far more than 20 requests a minute, because one comic can
        cost several — which is how a run earned 429s while sitting at
        the "safe" worker count. The gate bounds requests directly, so
        the worker count is free to be whatever the I/O wants again.
        """
        logger.info(f"Running {len(paths)} files with {jobs} workers")
        try:
            self._run_pool(paths, jobs)
        finally:
            # The pool has joined every worker, so none is left asleep to
            # wake: end the process-wide cancel with the pool that set it,
            # or every later retry in the process is refused.
            retry.clear_cancel()

    def _run_pool(self, paths: list[Path], jobs: int) -> None:
        """Run files in a pool that an abort or Ctrl-C ends as a whole."""
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
            except (OnlineLookupAbortedError, KeyboardInterrupt):
                # Wake the workers in flight from their retry sleeps, or
                # the join below waits them out, up to an hour each, and
                # stop them before their next prompt or source.
                retry.request_cancel()
                self._online_state.abort()
                raise
            finally:
                # Any way out -- an abort, Ctrl-C -- drops every file
                # still queued, so it actually ends the batch. Workers
                # already in flight finish: the pool joins them on the
                # way out.
                executor.shutdown(wait=False, cancel_futures=True)

    def run(self) -> None:
        """Run actions with config."""
        outcome_stats.reset()
        self.failure_count = 0
        self._cover_destinations = CoverDestinations()
        try:
            self._run_inner()
        finally:
            for line in outcome_stats.summary_lines():
                logger.info(line)
            _close_shared_online_sessions()

    def _maybe_auto_engage_effort(self, batch_size: int) -> None:
        """
        Auto-engage `effort=minimal` for large unattended runs.

        Mutates `self._config` in place (well, replaces via
        `dataclasses.replace`) so downstream Comicbox instances see the
        engaged effort. No-op when:

        - `online` isn't enabled (the only consumer of effort)
        - batch is small (single-fixture interactive use)
        - user pinned the global effort or any per-source effort

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
        # Stamp the outgoing User-Agent before any client is built: API
        # clients bake the header in at construction and are memoized per
        # credential set, so this is the only moment it can be set. Metron
        # operators read these logs, and `cli; jobs=N` is what tells them
        # a burst came from one process's thread pool rather than from
        # several processes sharing a token.
        set_user_agent_context("cli", jobs=jobs)
        # Expand paths up-front so we know the batch size for
        # auto-engagement, and how many comics an `--id` would reach.
        # Serial offline dispatch still calls `run_on_file`, which handles
        # directory expansion under `--recurse`, so its processing is
        # unchanged.
        paths = self._expand_paths()
        if self._config.online.lookup.ids and len(paths) > 1:
            # The CLI counts the paths as typed; a directory under -r
            # would otherwise tag every comic in it as the one issue.
            reason = f"--id requires exactly one comic, {len(paths)} found"
            raise UsageError(reason)
        # Fast path: single file or no parallelism. Preserves the original
        # one-call-per-path control flow including its recurse handling.
        if jobs <= 1:
            self._same_files = _same_files(paths)
            self._maybe_auto_engage_effort(len(paths))
            self._note_series_clusters(paths)
            if self._config.online.lookup.enabled:
                # Online serial runs dispatch over the EXPANDED, clustered
                # list so the series cache sees same-series files
                # back-to-back. Offline runs keep the original
                # one-call-per-configured-path control flow, which is what
                # `--recurse` directory handling is written against.
                for path in self._order_for_series_batching(paths, jobs):
                    self._run_one(path)
                return
            for raw in self._config.paths or ():
                self._run_one(raw)
            return

        # Parallel path: the thread pool sees the flat path list.
        if not paths:
            logger.warning("No files to process")
            return
        self._same_files = _same_files(paths)
        self._maybe_auto_engage_effort(len(paths))
        self._note_series_clusters(paths)
        if len(paths) == 1:
            self._run_one(paths[0])
            return
        self._run_parallel(self._order_for_series_batching(paths, jobs), jobs)
