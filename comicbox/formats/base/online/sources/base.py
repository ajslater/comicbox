"""
OnlineSource abstract base class.

Each concrete subclass wraps one upstream API client (mokkari, simyan, …)
behind a uniform contract the lookup mixin can drive.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger
from platformdirs import user_cache_path

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.series_filter import max_results_for, threshold_for

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable, Sequence

    from comicbox.config.settings import OnlineSettings, OnlineSourceCredentials
    from comicbox.formats import MetadataFormats
    from comicbox.formats.base.online.profile import Candidate, ComicProfile
    from comicbox.formats.sources import MetadataSources

# Cache paths already wiped this process under CacheMode.REFRESH.
_refreshed_cache_paths: set[str] = set()
_refresh_lock = threading.Lock()


def refresh_cache_unlink_once(cache_path: Path) -> None:
    """
    Delete a response-cache file once per process for CacheMode.REFRESH.

    REFRESH means "discard stale state at run start", not "disable
    caching". Clients are rebuilt during a run (and sources per file), so
    an unguarded unlink wiped the response cache between calls — e.g.
    between search() and get() of the same file — defeating the
    +1-API-call-per-unique-volume amortization get() relies on and
    re-spending API budget on every file of a --refresh-cache batch.
    """
    with _refresh_lock:
        if str(cache_path) in _refreshed_cache_paths:
            return
        _refreshed_cache_paths.add(str(cache_path))
    if cache_path.exists():
        cache_path.unlink()
        logger.debug(f"refresh-cache: removed {cache_path}")


class OnlineSource(ABC):
    """
    Contract every online provider must implement.

    Subclasses set the three `ClassVar` identifiers below and implement
    `is_configured`, `get`, and (in M3 onward) `search`.
    """

    name: ClassVar[str]
    metadata_source: ClassVar[MetadataSources]
    metadata_format: ClassVar[MetadataFormats]

    def __init__(
        self,
        credentials: OnlineSourceCredentials,
        settings: OnlineSettings,
    ) -> None:
        """Store refs needed for client construction."""
        self._credentials = credentials
        self._settings = settings
        # Per-method call counters for calibration / cost telemetry.
        # Counts INVOCATIONS at our wrapper level — includes cache hits
        # (since we can't distinguish them without peeking inside
        # simyan/mokkari) and counts retries as separate invocations
        # (each retry attempt is a real send when the cache miss). The
        # harness snapshots the dict before each fixture and diffs
        # after, which gives a per-fixture cost upper bound that's
        # exact for cold-cache runs and over-counts for warm-cache
        # runs by the cache-hit fraction. Good enough for Phase B
        # comparison; refine later if needed.
        self.api_call_counts: dict[str, int] = {}
        self.on_rate_limit: Any = None
        # Optional retry-sleep override consumed by the with_retry decorator
        # at call time (see retry._resolve_sleep). OnlineSession wires this
        # to its cancel event so callers can interrupt rate-limit waits; the
        # callable may raise to abort the retry loop.
        self.retry_sleep: Any = None
        # Lazily-built upstream client (simyan/mokkari), one per source
        # lifetime. Without this, every public method call constructed a
        # fresh client — new HTTP session, sqlite connection, limiter.
        self._client: Any = None

    def _record_api_call(self, method: str) -> None:
        """Bump `api_call_counts[method]`. Called by source-internal wrappers."""
        self.api_call_counts[method] = self.api_call_counts.get(method, 0) + 1

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the source has every credential it needs."""

    @abstractmethod
    def get(self, issue_id: int) -> dict[str, Any]:
        """
        Fetch a full issue record by upstream id, return as a plain dict.

        The shape is whatever the upstream library returns post-`model_dump`
        (or equivalent). Comicbox's per-source transform converts it to the
        internal schema.
        """

    @abstractmethod
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Build search criteria from a comic profile and return candidates.

        Each candidate carries display fields, the upstream id, and any
        precomputed cover hash. The matcher scores them; the lookup mixin
        decides AUTO_WRITE / PROMPT / SKIP / NO_MATCH.
        """

    def lookup_issue(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        """
        Direct volume-scoped issue lookup; bypasses the fuzzy search path.

        Series-first batching (plan §3.10) caches a resolved ``volume_id``
        per series fingerprint once per session. Subsequent comics in the
        same series skip the expensive ``search`` call and ask the source
        "what's issue N in volume V" directly — same rate-limit budget,
        cheaper per-call and unambiguous on healthy data sources.

        Return one Candidate when the lookup finds a matching issue, or
        None when it doesn't. None signals the caller to fall back to the
        normal search path (the cache entry stays unchanged so the
        first-writer-wins discipline holds).

        Sources that haven't implemented this raise NotImplementedError;
        callers detect that via try/except and fall back to ``search``.

        Failure semantics live here so each source only implements the
        actual API call (`_lookup_issue_in_volume`): source-side errors
        are logged and degrade to None (fall back to search), abort
        signals propagate, NotImplementedError propagates.
        """
        try:
            return self._lookup_issue_in_volume(volume_id, issue_number)
        except NotImplementedError:
            raise
        except OnlineLookupAbortedError:
            raise
        except Exception as exc:
            logger.warning(
                f"online {self.name}: lookup_issue(volume_id={volume_id}, "
                f"number={issue_number!r}) failed: {exc}"
            )
            return None

    def _lookup_issue_in_volume(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        """One volume-scoped API call; sources without a fast path omit it."""
        raise NotImplementedError

    # -- shared scaffolding ---------------------------------------------------

    def _resolve_response_cache(self) -> tuple[Path, datetime.timedelta] | None:
        """
        Apply the response-cache mode policy shared by every source.

        Returns None when caching is OFF; otherwise (cache_path, ttl).
        REFRESH unlinks the cache once per process (discard at run
        start). The source wraps the result in its vendor cache class.
        """
        from comicbox.config.settings import CacheMode

        cache_mode = self._settings.cache.mode
        if cache_mode is CacheMode.OFF:
            return None
        cache_path = self.cache_db_path()
        if cache_mode is CacheMode.REFRESH:
            refresh_cache_unlink_once(cache_path)
        return cache_path, self._settings.cache.ttl

    def _effort_max_results(self, default: int) -> int:
        """Resolve the per-effort discovery breadth cap for this source."""
        from comicbox.config.settings import resolve_effort

        return max_results_for(
            resolve_effort(self._settings, self.name), default=default
        )

    def _effort_name_threshold(self) -> float:
        """Resolve the per-effort pre-call name-filter threshold."""
        from comicbox.config.settings import resolve_effort

        return threshold_for(resolve_effort(self._settings, self.name))

    def _log_discovery_sample(
        self,
        items: Sequence[Any],
        labeler: Callable[[Any], str],
        *,
        noun: str,
        query: str,
    ) -> None:
        """Debug-log a sample of discovery results (shared wording)."""
        sample_size = 5
        sample = ", ".join(labeler(i) for i in items[:sample_size])
        if len(items) > sample_size:
            sample += " ..."
        logger.debug(
            f"online {self.name}: {len(items)} candidate {noun} for {query}: {sample}"
        )

    def cache_db_path(self, suffix: str = "cache") -> Path:
        """
        Resolve the cache sqlite path for this source.

        Honours `online.cache_dir` when set; otherwise uses the platformdirs
        user cache path for comicbox. Creates the parent directory.
        """
        cache_dir = self._settings.cache.dir
        if cache_dir is None:
            cache_dir = user_cache_path("comicbox") / "online"
        cache_dir = Path(cache_dir).expanduser()
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{self.name}_{suffix}.sqlite"
