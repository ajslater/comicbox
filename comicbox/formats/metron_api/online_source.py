"""
Metron API source via mokkari.

M2 wires the `--id metron:N` path: instantiate a session with credentials
from the resolution chain, fetch one issue by id, dump the Pydantic model
to a plain dict, and hand it back to `ComicboxOnlineLookup` for transform
and merge. M3 adds search.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, ClassVar, Final

from loguru import logger
from typing_extensions import override

from comicbox.enums.comicbox import IdSources
from comicbox.events import SKIP_QUOTA_RESERVED
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.base.online.rate_limits import METRON_DEFAULT_PER_MINUTE
from comicbox.formats.base.online.retry import RetryCategory, with_retry
from comicbox.formats.base.online.sources.base import (
    OnlineSource,
)
from comicbox.formats.base.online.warn_once import warn_once
from comicbox.formats.sources import MetadataSources
from comicbox.identifiers import DEFAULT_ID_TYPE
from comicbox.identifiers.identifiers import get_identifier_url
from comicbox.version import user_agent

if TYPE_CHECKING:
    from mokkari.session import RateLimitStatus, Session

    from comicbox.formats.base.online.profile import ComicProfile

# Sessions are shared across the credential set that built them (see
# `_get_session`), keyed by (user, password) — not `db_path` like the old
# pyrate_limiter override cache, since there's no bucket to key by anymore.
# A shared `Session` gives `Runner._run_parallel`'s thread pool
# (comicbox/run.py) one response cache and one consistent
# `rate_limit_status` instead of each file's source starting cold;
# mokkari>=4.0.1 makes this safe (thread-safe `SqliteCache`,
# `rate_limit_status` lock). Sharing the observation was never enough to
# stay inside the window, though — `_gate_cache` below is what enforces
# it.
#
# Contract: FIRST BUILD WINS. The Session (and the response cache baked
# into it) is constructed from the settings of whichever source instance
# hits the cache miss; later same-credential sources reuse it even if
# their own cache settings differ (we warn once when they do — see
# `_get_or_build_shared_session`). Keying by cache config instead would
# split `rate_limit_status` across sessions and defeat the sharing.
# Entries are deliberately never evicted or closed: the cache is bounded
# by distinct credential sets used in one process, and mokkari's
# SqliteCache exposes no close() to release anyway.
_session_cache: dict[tuple[str, str, str], tuple[Any, tuple]] = {}
_session_cache_lock = threading.Lock()

# One `RateGate` per credential set, built alongside that set's Session
# and under the same lock. The gate is what actually keeps comicbox
# inside Metron's 20/min window (see `comicbox/formats/base/online/
# rate_gate.py`); sharing the Session was only ever enough to share
# mokkari's *observation* of the limit, not to enforce it.
_gate_cache: dict[tuple[str, str, str], RateGate] = {}


# Prefetched issue lists, keyed by Metron series id: {number: BaseIssue}.
# Filled by `MetronOnlineSource.prefetch_volume` for a series a batch
# holds many comics from, so the rest of that cluster answers "issue N in
# volume V" from memory instead of one `issues_list` each.
#
# Bounded, unlike `_session_cache`: this holds real payloads, and a big
# library run touches many series. Oldest-first eviction is right here —
# a batch is ordered by series, so the series that filled the oldest
# entry is the one the run has finished with.
_PREFETCH_MAX_VOLUMES: Final[int] = 64
# Metron's DRF `PAGE_SIZE`, which decides how many requests listing a
# whole series takes.
_METRON_PAGE_SIZE: Final[int] = 100
# Below this a prefetch cannot pay for itself: the `series(id)` call plus
# at least one list page is already 2 requests, so a 2-comic cluster
# breaks even at best.
_PREFETCH_MIN_CLUSTER: Final[int] = 3

_prefetch_cache: OrderedDict[int, dict[str, Any]] = OrderedDict()
_prefetch_lock = threading.Lock()


def _has_prefetch(volume_id: int) -> bool:
    """Whether this volume's issue list has already been pulled."""
    with _prefetch_lock:
        return volume_id in _prefetch_cache


def _store_prefetch(volume_id: int, by_number: dict[str, Any]) -> None:
    """Record a volume's issue list, evicting the oldest volume if full."""
    with _prefetch_lock:
        _prefetch_cache[volume_id] = by_number
        _prefetch_cache.move_to_end(volume_id)
        while len(_prefetch_cache) > _PREFETCH_MAX_VOLUMES:
            _prefetch_cache.popitem(last=False)


def _prefetched_issue(volume_id: int, number: str) -> Any:
    """Return a prefetched `BaseIssue` for this volume and number, or None."""
    with _prefetch_lock:
        volume = _prefetch_cache.get(volume_id)
        return volume.get(number) if volume else None


def shared_gate(
    user: str | None, password: str | None, key: str | None = None
) -> RateGate | None:
    """
    Return a credential set's rate gate, or None if nothing built one yet.

    Read-only accessor for callers that want the pacing counters without
    holding a source instance (the end-of-run summary, tests).
    """
    with _session_cache_lock:
        return _gate_cache.get((user or "", password or "", key or ""))


def shared_session_rate_limit_status(
    user: str | None, password: str | None, key: str | None = None
) -> RateLimitStatus | None:
    """
    Rate-limit state of the shared mokkari session for a credential set.

    Returns the live ``RateLimitStatus`` mokkari tracks from Metron's
    ``X-RateLimit-*`` response headers, or None when no session exists for
    these credentials in this process yet (nothing has hit the network).
    Window fields are None until Metron reports them. The empty-credential
    normalization mirrors ``_get_or_build_shared_session``'s cache key.
    """
    cache_key = (user or "", password or "", key or "")
    with _session_cache_lock:
        entry = _session_cache.get(cache_key)
    if entry is None:
        return None
    session, _ = entry
    return session.rate_limit_status


def _bi_series_name(bi_series: Any) -> str | None:
    """Pull a name off `BaseIssue.series` when the nested object exists."""
    return getattr(bi_series, "name", None) if bi_series is not None else None


def _bi_series_id(bi_series: Any) -> int | None:
    """Pull an id off `BaseIssue.series` when the nested object exists."""
    return getattr(bi_series, "id", None) if bi_series is not None else None


def _issue_url(issue_id: int) -> str:
    """
    Metron's web page for an issue.

    mokkari's `BaseIssue` carries no url at all, and the full `Issue`'s
    `resource_url` is the API endpoint rather than a page a human should
    be shown. Metron routes `issue/<int:pk>/` through a redirect to the
    slug url, so the numeric id is a stable public link.
    """
    return get_identifier_url(IdSources.METRON.value, DEFAULT_ID_TYPE, str(issue_id))


# Throttle wording, checked before anything else: a throttle response
# served with a status other than 429 (a CDN 403/420, or a 2xx "Request
# was throttled" detail body) must retry even when the same message also
# mentions credentials or an api key.
_RATE_LIMIT_MARKERS: Final = ("rate limit", "throttl", "too many requests")

# Statuses that mean "these credentials will never work". Metron's 429 is
# already a RateLimitError, so it never reaches the status check.
_AUTH_STATUSES: Final = frozenset({401, 403})

# Credential wording, used only for the ApiError paths that carry no
# chained response (the 2xx `detail` body and pydantic validation).
# Words only, never bare status numbers: an ApiError message embeds
# repr(HTTPError) with the full URL, so "401"/"403" substring-match
# Metron ids like /api/issue/14031/ and would strand a retriable 502.
# No bare "auth" either — it substring-matches "author", and these
# messages carry pydantic dumps of comic metadata with creator fields.
_AUTH_MARKERS: Final = (
    "unauthorized",
    "forbidden",
    "invalid username",
    "invalid password",
    "invalid token",
)


def _classify_api_error(exc: BaseException) -> RetryCategory:
    """
    Classify mokkari's catch-all ApiError.

    mokkari collapses non-429 HTTP errors, connection failures, bad JSON,
    2xx {"detail": ...} bodies and pydantic failures into this one class.
    Every HTTP failure is chained (``raise ApiError(msg) from err``), so
    when the requests error carries a response its status is authoritative
    and the message is not worth reading; the remaining paths have no
    status at all and leave only the wording to go on.
    """
    msg = str(exc).lower()
    if any(marker in msg for marker in _RATE_LIMIT_MARKERS):
        return RetryCategory.RATE_LIMIT
    status = getattr(getattr(exc.__cause__, "response", None), "status_code", None)
    if status is not None:
        return (
            RetryCategory.AUTH if status in _AUTH_STATUSES else RetryCategory.TRANSIENT
        )
    if any(marker in msg for marker in _AUTH_MARKERS):
        return RetryCategory.AUTH
    return RetryCategory.TRANSIENT


class MetronOnlineSource(OnlineSource):
    """Wraps mokkari for the Metron API."""

    name: ClassVar[str] = "metron"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.METRON_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.METRON_API
    # Every send goes through this credential set's `RateGate` (see
    # `paced_session`), so the retry loop must not also sleep the hint.
    paces_rate_limit: ClassVar[bool] = True

    @override
    def is_configured(self) -> bool:
        """Metron accepts an API token (key), or both username and password."""
        credentials = self._credentials
        return bool(credentials.key or (credentials.user and credentials.password))

    @override
    @staticmethod
    def classify_retry_exception(exc: BaseException) -> RetryCategory | None:
        """Classify mokkari's exceptions; see `_classify_api_error`."""
        from mokkari.exceptions import (
            ApiError,
            AuthenticationError,
            CacheError,
            RateLimitError,
        )

        if isinstance(exc, RateLimitError):
            return RetryCategory.RATE_LIMIT
        if isinstance(exc, AuthenticationError):
            # Raised only by Session.__init__ for missing local credentials.
            return RetryCategory.AUTH
        if isinstance(exc, CacheError):
            # Raised on the first request, not in Session.__init__, when the
            # cache object lacks get()/store(): a wiring bug, never transient.
            return RetryCategory.INVALID
        if isinstance(exc, ApiError):
            return _classify_api_error(exc)
        return None

    def _get_cache(self) -> Any:
        resolved = self._resolve_response_cache()
        if resolved is None:
            return None
        from mokkari.sqlite_cache import SqliteCache

        from comicbox.formats.base.online.vacuum import vacuum_if_bloated

        cache_path, ttl = resolved
        # mokkari's SqliteCache treats `expire` as a number of *days*
        # (timedelta(days=expire)), not seconds. Round up so a sub-day TTL
        # still expires after at least one day rather than collapsing toward
        # 0 (which mokkari reads as "no expiry").
        expire = (
            math.ceil(ttl.total_seconds() / 86400) if ttl.total_seconds() > 0 else None
        )
        # mokkari's SqliteCache cleans up expired rows on open; reclaim the
        # freed pages if the file has gotten bloated.
        cache = SqliteCache(db_name=str(cache_path), expire=expire)
        vacuum_if_bloated(cache_path)
        return cache

    def _get_session(self) -> Session:
        """
        Return the process-wide mokkari client shared by this credential set.

        Sources are rebuilt per file (see `MetronOnlineSource.__init__` via
        `OnlineSource`), so without sharing at module scope every file's
        source would get its own `Session` with its own blank
        `rate_limit_status` — none of them would ever see another worker's
        rate-limit state. Memoizing by (user, password, key) lets every thread in
        `Runner._run_parallel`'s pool (comicbox/run.py) that logs in with the
        same credentials observe one shared, continuously-updated
        `rate_limit_status` — and, more importantly, queue behind one
        `RateGate`. Pacing is what makes sharing threads (not processes)
        worthwhile: a second process would get a second gate and the two
        would have to split the window between them.
        """
        if self._client is None:
            # Warn here rather than in _build_session so ignored-config
            # warnings don't depend on winning the session-cache miss;
            # warn_once keeps them at one line per process either way.
            self._warn_ignored_url()
            self._warn_ignored_rate_limit_overrides()
            self._warn_deprecated_basic_auth()
            self._client = self._get_or_build_shared_session()
        return self._client

    def _session_config_signature(self) -> tuple:
        """Return the per-instance settings a built Session bakes in."""
        cache = self._settings.cache
        return (cache.mode, cache.dir, cache.ttl)

    def _credential_key(self) -> tuple[str, str, str]:
        """Identity of the credential set a Session and gate are shared by."""
        return (
            self._credentials.user or "",
            self._credentials.password or "",
            self._credentials.key or "",
        )

    def _get_or_build_shared_session(self) -> Session:
        key = self._credential_key()
        signature = self._session_config_signature()
        with _session_cache_lock:
            entry = _session_cache.get(key)
            if entry is None:
                gate = _gate_cache.get(key)
                if gate is None:
                    gate = self._build_gate()
                    _gate_cache[key] = gate
                session = self._build_session(gate)
                _session_cache[key] = (session, signature)
                return session
        session, built_signature = entry
        if built_signature != signature:
            # First build wins (see the _session_cache comment); tell the
            # user their differing cache config is not taking effect.
            warn_once(
                f"{self.name}:session-config-mismatch",
                f"online {self.name}: reusing the existing shared mokkari "
                "session; this instance's differing cache settings "
                f"{signature} are ignored in favor of the session's "
                f"{built_signature}",
            )
        return session

    def _build_gate(self) -> RateGate:
        """
        Build this credential set's rate gate.

        ``rate_limit.per_minute`` is honored here as a CEILING on the
        server-reported burst limit, never a raise. That gives the knob a
        real meaning again for the case it exists for: an embedder
        running several processes against one Metron token has one gate
        per process, and the only way to keep their sum inside the
        server's window is for each to take a share.
        """
        from comicbox.config.online.settings import resolve_rate_limit

        limits = resolve_rate_limit(self._settings, self.name)
        return RateGate(
            default_limit=METRON_DEFAULT_PER_MINUTE,
            config_limit=limits.per_minute,
        )

    def _build_session(self, gate: RateGate | None = None) -> Session:
        """
        Build a paced mokkari Session.

        Not `mokkari.api()`: that factory hardcodes `Session`, and the
        pacing has to live inside the client (see `paced_session`). The
        keyword set is api()'s, minus `dev_mode`, which comicbox has no
        setting for.
        """
        from comicbox.formats.metron_api.paced_session import PacedSession

        return PacedSession(
            gate=gate,
            username=self._credentials.user,  # mokkari keyword
            passwd=self._credentials.password,
            cache=self._get_cache(),
            user_agent=user_agent(),
            # mokkari prefers the token over username/passwd when both are
            # set; None falls back to basic auth.
            api_token=self._credentials.key,
        )

    def _gate(self) -> RateGate | None:
        """Return the shared rate gate, once a session has been built."""
        with _session_cache_lock:
            return _gate_cache.get(self._credential_key())

    def _warn_ignored_url(self) -> None:
        if self._credentials.url:
            # mokkari's api() factory has no URL-override parameter (only
            # dev_mode for the dev API), so --auth metron:url= can't
            # actually be honored. Warn so the user notices.
            warn_once(
                f"{self.name}:api-url",
                f"online {self.name}: --auth metron:url= is a no-op "
                f"(mokkari has no base_url override); ignoring "
                f"{self._credentials.url!r}",
            )

    def _warn_deprecated_basic_auth(self) -> None:
        # Only fires when basic auth is what mokkari will actually use: a
        # token, when present, wins over username/passwd.
        if not self._credentials.key:
            warn_once(
                f"{self.name}:basic-auth-deprecated",
                f"online {self.name}: username/password authentication is "
                "deprecated and will be removed in a future release. "
                "Generate an API token on your metron.cloud account page and "
                "set it with --auth metron:key=TOKEN or the "
                "COMICBOX_ONLINE__AUTH__METRON__KEY environment variable.",
            )

    def _warn_ignored_rate_limit_overrides(self) -> None:
        """
        Warn about `per_day`, which still has nowhere to go.

        `per_minute` is honored again — `_build_gate` takes it as a
        ceiling on the burst window. `per_day` is not: Metron reports the
        sustained window per user (donor tiers raise it), the gate tracks
        what the server says is left, and comicbox keeps no cross-run
        tally of its own to enforce a smaller daily number against.
        """
        from comicbox.config.online.settings import resolve_rate_limit

        limits = resolve_rate_limit(self._settings, self.name)
        if limits.per_day is not None:
            warn_once(
                f"{self.name}:rate-limit-override",
                f"online {self.name}: rate_limit.per_day is ignored — "
                "Metron reports the remaining daily quota per user in its "
                "response headers and comicbox paces against that. Use "
                "rate_limit.per_minute to take a smaller share of the "
                "burst window.",
            )

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """Fetch one Metron issue by id; return its model dump."""
        session = self._get_session()
        self._record_api_call("issue")
        issue = session.issue(issue_id)
        if issue is None:
            msg = f"metron: issue {issue_id} not found"
            raise LookupError(msg)
        return issue.model_dump(mode="json")

    def _build_common_issue_filters(
        self,
        profile: ComicProfile,
        *,
        cover_year_override: int | None,
        include_volume: bool,
    ) -> dict[str, Any]:
        """
        Build filters shared by the series_id-keyed and series_name-keyed builders.

        ``cover_year_override`` lets the ±1 retry-on-miss path supply a
        neighboring year. When None, ``profile.year`` is used as-is.

        ``include_volume`` is the toggle for the drop-volume retry path:
        passing False omits Metron's ``series_volume`` filter even when
        ``profile.volume`` is set.
        """
        params: dict[str, Any] = {}
        # Strip leading zeros — Metron stores `number` without padding.
        if number := strip_issue_leading_zeros(profile.issue):
            params["number"] = number
        cover_year = (
            cover_year_override if cover_year_override is not None else profile.year
        )
        if cover_year is not None:
            params["cover_year"] = cover_year
        if include_volume and profile.volume is not None:
            params["series_volume"] = profile.volume
        return params

    def _build_issue_params(
        self,
        profile: ComicProfile,
        series_id: int,
        *,
        cover_year_override: int | None = None,
        include_volume: bool = True,
    ) -> dict[str, Any]:
        """
        Build the `issues_list` params filtering on a resolved series id.

        IMPORTANT: the FK filter param is ``series_id``, NOT ``series``.
        Mokkari's docstring example (`{"series": 1}`) is misleading —
        Metron's DRF backend silently ignores `series` as an unknown
        filter and returns issues matched only by the remaining params
        (number + cover_year), leaking thousands of unrelated 2020 #1s
        when querying for AR #1 (2020). Confirmed empirically against
        the live Metron API on 2026-05-13.
        """
        params: dict[str, Any] = {"series_id": series_id}
        params.update(
            self._build_common_issue_filters(
                profile,
                cover_year_override=cover_year_override,
                include_volume=include_volume,
            )
        )
        return params

    def _build_issue_params_by_name(
        self,
        profile: ComicProfile,
        *,
        cover_year_override: int | None = None,
        include_volume: bool = True,
    ) -> dict[str, Any]:
        """
        Build the `issues_list` params filtering directly on series_name.

        Confirmed against Metron's live `IssueFilter`
        (`comicsdb/filters/issue.py`): `series_name` reuses the identical
        `unaccent__icontains` whitespace-AND-of-terms predicate that
        `series_list`'s own `name` filter applies to `Series.name` — so
        this has the same recall as the old "discover series by name,
        then filter issues by series id" two-step, at one call instead of
        up to 21.
        """
        params: dict[str, Any] = {"series_name": profile.series}
        params.update(
            self._build_common_issue_filters(
                profile,
                cover_year_override=cover_year_override,
                include_volume=include_volume,
            )
        )
        return params

    def _to_candidate(
        self,
        base_issue: Any,
        *,
        series_id: int | None = None,
    ) -> Candidate:
        """
        Map a mokkari `BaseIssue` to a Candidate.

        ``series_id`` lets a caller that already knows the series id
        (the explicit `--series-id` fast path, or the volume-scoped
        `lookup_issue` fast path) supply it directly. The by-name search
        path doesn't need to — since mokkari 3.28.0 / Metron server
        commit 3b1e46b, `BaseIssue.series` (`BasicSeries`) carries a real
        `.id`, so `_bi_series_id` recovers it from the search result
        itself.
        """
        bi_series = getattr(base_issue, "series", None)
        summary = CandidateSummary(
            series=_bi_series_name(bi_series) or "",
            issue=base_issue.number,
            year=base_issue.cover_date.year if base_issue.cover_date else None,
            publisher=None,  # BaseIssue from search omits publisher
            page_count=None,
            cover_url=str(base_issue.image) if base_issue.image else None,
            variant_label=None,
        )
        return Candidate(
            source=self.name,
            issue_id=base_issue.id,
            summary=summary,
            url=_issue_url(base_issue.id),
            precomputed_cover_hash=getattr(base_issue, "cover_hash", None) or None,
            volume_id=series_id if series_id is not None else _bi_series_id(bi_series),
        )

    @override
    def _lookup_issue_in_volume(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        """
        Volume-scoped issue lookup; cheaper than the fuzzy search path.

        Calls ``issues_list`` filtered by ``series_id`` + ``number`` — one
        request, returns ≤1 result on healthy data. Returns None without
        a request when there is no issue number: an unfiltered
        ``series_id`` query pages through the whole series and the first
        row would win. The base class's ``lookup_issue`` wrapper owns the
        failure semantics.
        """
        number = strip_issue_leading_zeros(issue_number)
        if not number:
            return None
        prefetched = _prefetched_issue(volume_id, number)
        if prefetched is not None:
            return self._to_candidate(prefetched, series_id=volume_id)
        session = self._get_session()
        params: dict[str, Any] = {"series_id": volume_id, "number": number}
        issues = self._issues_list_with_retry(session, params)
        issue_list = list(issues)
        if not issue_list:
            return None
        # On the rare multi-result case (cover variants under one
        # `number`), accept the first — caller would otherwise need to
        # decide between variants which is a different problem.
        return self._to_candidate(issue_list[0], series_id=volume_id)

    @override
    def prefetch_volume(self, volume_id: int, cluster_size: int) -> None:
        """
        Pull a whole series' issue list once instead of once per comic.

        With `PAGE_SIZE=100` a series is one or a few pages, so a long run
        costs `1 + pages` requests to list instead of one `issues_list`
        per comic. Only worth it when that is actually cheaper than the
        lookups it replaces, which is what the `series(id)` call buys: its
        `issue_count` says how many pages the list will take before
        committing to fetching it.

        The `issue(id)` detail fetch still happens per comic — `BaseIssue`
        carries no credits or characters — so this takes a cluster from
        about two requests per comic to about one.

        Best effort throughout: anything that goes wrong leaves the
        per-comic path exactly as it was.
        """
        if cluster_size < _PREFETCH_MIN_CLUSTER or _has_prefetch(volume_id):
            return
        try:
            self._prefetch_volume_issues(volume_id, cluster_size)
        except OnlineLookupAbortedError:
            raise
        except Exception as exc:
            logger.debug(
                f"online {self.name}: series prefetch for volume {volume_id} "
                f"failed: {exc}; falling back to per-issue lookups"
            )

    def _prefetch_volume_issues(self, volume_id: int, cluster_size: int) -> None:
        """Do the two-step prefetch; see `prefetch_volume` for the policy."""
        session = self._get_session()
        series = self._series_with_retry(session, volume_id)
        issue_count = getattr(series, "issue_count", None) if series else None
        if not issue_count:
            return
        pages = math.ceil(issue_count / _METRON_PAGE_SIZE)
        # `1` for the series() call already spent, plus a page each. The
        # comparison is against what the cluster would otherwise pay: one
        # issues_list per comic.
        if 1 + pages >= cluster_size:
            logger.debug(
                f"online {self.name}: not prefetching volume {volume_id} — "
                f"{1 + pages} requests to list {issue_count} issues is not "
                f"cheaper than {cluster_size} per-issue lookups"
            )
            return
        issues = self._issues_list_with_retry(session, {"series_id": volume_id})
        by_number: dict[str, Any] = {}
        for issue in issues:
            number = strip_issue_leading_zeros(getattr(issue, "number", None))
            # First writer wins, mirroring `_lookup_issue_in_volume`'s
            # "accept the first" rule for cover variants sharing a number.
            if number and number not in by_number:
                by_number[number] = issue
        _store_prefetch(volume_id, by_number)
        logger.info(
            f"online {self.name}: prefetched {len(by_number)} issues of volume "
            f"{volume_id} in {1 + pages} requests, for {cluster_size} comics"
        )

    @with_retry(max_retries=1)
    def _series_with_retry(self, session: Session, series_id: int) -> Any:
        """
        Per-call retry wrapper around `session.series`.

        Deliberately a tighter budget than the rest of the source. This
        call only decides whether a prefetch is worth doing, and there is
        a working fallback one line away, so burning the user's full
        retry budget (and its 31s of backoff) on it would cost more than
        the optimization can ever save. Rate-limit errors keep their own
        budget, which the gate makes free to spend.
        """
        self._record_api_call("series")
        return session.series(series_id)

    def _search_by_explicit_series_id(
        self, session: Session, profile: ComicProfile, series_id: int
    ) -> list[Candidate]:
        """
        Single-call issue lookup against a user-supplied series id.

        Not decorated with ``@with_retry()``: the API call inside
        (`_issues_list_with_retry`) carries its own retry budget, and an
        outer decorator would multiply budgets (8x8 attempts) by replaying
        the whole lookup after the inner budget is already exhausted.
        """
        # The user has been explicit about the series id; the soft volume
        # filter would just risk false-zero. Trust the supplied id.
        params = self._build_issue_params(profile, series_id, include_volume=False)
        try:
            issues = self._issues_list_with_retry(session, params)
        except Exception as exc:
            logger.warning(
                f"online {self.name}: issue-list for series id {series_id} "
                f"failed: {exc}"
            )
            raise
        return [self._to_candidate(i, series_id=series_id) for i in issues]

    @override
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search Metron via a direct issues_list(series_name=...) call.

        No series-discovery step, no per-series fan-out.

        Not decorated with ``@with_retry()``: every API call inside is
        individually retried by its leaf wrapper (`_issues_list_with_retry`),
        matching the ComicVine source. An outer decorator here would
        multiply retry budgets (8x8 whole-search replays of already-
        exhausted inner budgets — hours of worst-case sleep).

        Metron's `series_name` issue-list filter (`comicsdb/filters/issue.py`,
        `IssueFilter.series_name`) reuses the identical icontains+unaccent,
        whitespace-AND-of-terms predicate that `series_list`'s own `name`
        filter applies — same recall as the old series_list → issues_list
        two-step, at 1 call instead of up to 21. Since mokkari 3.28.0 /
        Metron server commit 3b1e46b, `BaseIssue.series.id` is populated
        directly on `issues_list` results, so `Candidate.volume_id` no
        longer requires a separate series-discovery step to resolve
        either.

        ``--series-id metron:<id>`` still short-circuits straight to a
        single `issues_list({series_id: ...})` call — unchanged.
        """
        # Owns its own lifetime: set when this search declines to run,
        # cleared here so it can never be read as the next comic's answer.
        self.reset_search_skip_reason()
        session = self._get_session()
        if not self._may_start_cold_search():
            return []
        explicit_sid = self._settings.lookup.series_ids.get(self.name)
        if explicit_sid is not None:
            return self._search_by_explicit_series_id(session, profile, explicit_sid)

        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search Metron "
                "(use --id metron:<id> for direct lookup, or --series-id metron:<id>)"
            )
            return []

        candidates = self._search_with_year_retry(session, profile, include_volume=True)

        # Drop-volume retry on miss. Filename-parsed `Vol. N` is moderately
        # reliable but inconsistent — some scanners drop it, some get the
        # number wrong. If the volume-filtered cycle (year-exact + Y±1)
        # returned nothing, retry the whole cycle without the volume
        # filter. Skipped if no volume was filtering in the first place.
        if not candidates and profile.volume is not None:
            logger.info(
                f"online {self.name}: 0 candidates with series_volume="
                f"{profile.volume}, retrying without the volume filter"
            )
            candidates = self._search_with_year_retry(
                session, profile, include_volume=False
            )

        return candidates

    def _may_start_cold_search(self) -> bool:
        """
        Whether the daily quota can still afford to START a search.

        Once Metron reports the sustained window down to its reserve, the
        gate stops admitting discretionary work. A search only begins a
        comic; the `issue(id)` fetch that follows a match is what
        finishes one. Spending the last of the day on new searches would
        leave a trail of comics that matched and were never written.

        Returning [] reads downstream as "no candidates", so the reason is
        recorded alongside it: the lookup reports a `Skipped` with
        `SKIP_QUOTA_RESERVED` rather than a NO_MATCH, since this comic was
        never actually looked at and should be tried again tomorrow.
        """
        gate = self._gate()
        if gate is None or gate.allow_cold_search():
            return True
        self._note_search_skipped(SKIP_QUOTA_RESERVED)
        logger.info(
            f"online {self.name}: daily quota nearly spent; skipping this "
            "search so the remaining budget finishes comics that matched"
        )
        return False

    def _fetch_candidates_by_name(
        self,
        session: Session,
        profile: ComicProfile,
        *,
        cover_year_override: int | None,
        include_volume: bool,
    ) -> list[Candidate]:
        """One issues_list call filtered by series_name (+ number/year/volume)."""
        params = self._build_issue_params_by_name(
            profile,
            cover_year_override=cover_year_override,
            include_volume=include_volume,
        )
        issues = self._issues_list_with_retry(session, params)
        return [self._to_candidate(i) for i in issues]

    def _search_with_year_retry(
        self,
        session: Session,
        profile: ComicProfile,
        *,
        include_volume: bool,
    ) -> list[Candidate]:
        """
        Year-exact pass plus ±1 retry on miss; volume filter is optional.

        Cover-date drift is real: a comic published in late 2019 can be
        cover-dated 2020-01. When the year-exact pass returns zero, retry
        with Y-1 then Y+1. Skipped if there's no year to relax.

        Failure semantics are deliberately asymmetric: the year-exact
        (primary) call's exception is logged and re-raised — a hard
        failure here means the whole search failed, not "0 results."
        Each ±1 retry attempt's exception is logged and swallowed so its
        sibling still gets a chance, mirroring the old per-series fan-out's
        "one bad target doesn't kill the others" resilience at the new
        unit of fan-out (retry attempts instead of series).
        """
        try:
            candidates = self._fetch_candidates_by_name(
                session,
                profile,
                cover_year_override=None,
                include_volume=include_volume,
            )
        except Exception as exc:
            logger.warning(
                f"online {self.name}: issue-list for series_name="
                f"{profile.series!r} failed: {exc}"
            )
            raise
        if not candidates and profile.year is not None:
            for delta in (-1, 1):
                retry_year = profile.year + delta
                logger.info(
                    f"online {self.name}: 0 candidates at year={profile.year}, "
                    f"retrying with cover_year={retry_year}"
                )
                try:
                    retry = self._fetch_candidates_by_name(
                        session,
                        profile,
                        cover_year_override=retry_year,
                        include_volume=include_volume,
                    )
                except OnlineLookupAbortedError:
                    # An abort ends the whole lookup; it is not a
                    # source-side failure to degrade past.
                    raise
                except Exception as exc:
                    logger.warning(
                        f"online {self.name}: issue-list retry at "
                        f"cover_year={retry_year} failed: {exc}"
                    )
                    continue
                candidates.extend(retry)
        return candidates

    @with_retry()
    def _issues_list_with_retry(
        self, session: Session, params: dict[str, Any]
    ) -> list[Any]:
        """
        Per-call retry wrapper around `session.issues_list`.

        `search()`'s year-retry cascade fires at most 3 calls per
        `include_volume` cycle (year-exact + Y-1 + Y+1), times at most 2
        cycles (with-volume, drop-volume) — at most 6 `issues_list` calls
        per search.

        `PacedSession` admits every one of those through this credential
        set's `RateGate`, so under `-j N` they queue instead of colliding
        and a 429 should not happen at all. It still can — another client
        on the same token, or a window we had not yet been told the shape
        of — and when it does, the gate absorbs the `Retry-After` hint
        and this decorator replays the single failed call rather than
        spamming "issue-list … failed" warnings and dropping the data.
        Because the source sets `paces_rate_limit`, the replay does not
        sleep the hint a second time; it blocks at the gate.

        `_record_api_call` counts one call here, but mokkari follows
        `next` pages inside it, so a result set longer than one Metron
        page costs more HTTP requests than the count shows. The
        production filters (series, number, cover_year) keep results
        well under a page.
        """
        self._record_api_call("issues_list")
        return session.issues_list(params=params)
