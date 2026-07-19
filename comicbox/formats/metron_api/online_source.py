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
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger
from typing_extensions import override

from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.retry import with_retry
from comicbox.formats.base.online.sources.base import (
    OnlineSource,
)
from comicbox.formats.base.online.warn_once import warn_once
from comicbox.formats.sources import MetadataSources
from comicbox.version import USER_AGENT

if TYPE_CHECKING:
    from mokkari.session import Session

    from comicbox.formats.base.online.profile import ComicProfile

# Sessions are shared across the credential set that built them (see
# `_get_session`), keyed by (user, password) — not `db_path` like the old
# pyrate_limiter override cache, since there's no bucket to key by anymore.
# A shared `Session` is what lets `Runner._run_parallel`'s thread pool
# (comicbox/run.py) see one consistent `rate_limit_status` across workers
# instead of each file's source starting cold; mokkari>=4.0.1 makes this
# safe (thread-safe `SqliteCache`, `rate_limit_status` lock).
#
# Contract: FIRST BUILD WINS. The Session (and the response cache baked
# into it) is constructed from the settings of whichever source instance
# hits the cache miss; later same-credential sources reuse it even if
# their own cache settings differ (we warn once when they do — see
# `_get_or_build_shared_session`). Keying by cache config instead would
# split `rate_limit_status` across sessions and defeat the sharing.
# Entries are deliberately never evicted or closed: the cache is bounded
# by distinct credential pairs used in one process, and mokkari's
# SqliteCache exposes no close() to release anyway.
_session_cache: dict[tuple[str, str], tuple[Any, tuple]] = {}
_session_cache_lock = threading.Lock()


def _bi_series_name(bi_series: Any) -> str | None:
    """Pull a name off `BaseIssue.series` when the nested object exists."""
    return getattr(bi_series, "name", None) if bi_series is not None else None


def _bi_series_id(bi_series: Any) -> int | None:
    """Pull an id off `BaseIssue.series` when the nested object exists."""
    return getattr(bi_series, "id", None) if bi_series is not None else None


def _bi_resource_url(base_issue: Any) -> str:
    """Return the issue's resource URL as a string; "" when missing."""
    url = getattr(base_issue, "resource_url", None)
    return str(url) if url else ""


class MetronOnlineSource(OnlineSource):
    """Wraps mokkari for the Metron API."""

    name: ClassVar[str] = "metron"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.METRON_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.METRON_API

    @override
    def is_configured(self) -> bool:
        """Metron requires both username and password."""
        return bool(self._credentials.user and self._credentials.password)

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
        rate-limit state. Memoizing by (user, password) lets every thread in
        `Runner._run_parallel`'s pool (comicbox/run.py) that logs in with the
        same credentials observe one shared, continuously-updated
        `rate_limit_status`, which is what actually makes sharing threads
        (not processes) worthwhile under mokkari>=4.0.1's reactive,
        header-driven rate limiting.
        """
        if self._client is None:
            # Warn here rather than in _build_session so ignored-config
            # warnings don't depend on winning the session-cache miss;
            # warn_once keeps them at one line per process either way.
            self._warn_ignored_url()
            self._warn_ignored_rate_limit_overrides()
            self._client = self._get_or_build_shared_session()
        return self._client

    def _session_config_signature(self) -> tuple:
        """Return the per-instance settings a built Session bakes in."""
        cache = self._settings.cache
        return (cache.mode, cache.dir, cache.ttl)

    def _get_or_build_shared_session(self) -> Session:
        key = (self._credentials.user or "", self._credentials.password or "")
        signature = self._session_config_signature()
        with _session_cache_lock:
            entry = _session_cache.get(key)
            if entry is None:
                session = self._build_session()
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

    def _build_session(self) -> Session:
        from mokkari import api

        return api(
            username=self._credentials.user,  # mokkari keyword
            passwd=self._credentials.password,
            cache=self._get_cache(),
            user_agent=USER_AGENT,
        )

    def _warn_ignored_url(self) -> None:
        if self._credentials.url:
            # mokkari's api() factory has no URL-override parameter (only
            # dev_mode for the dev API), so --api-url metron:<url> can't
            # actually be honored. Warn so the user notices.
            warn_once(
                f"{self.name}:api-url",
                f"online {self.name}: --api-url is a no-op for metron "
                f"(mokkari has no base_url override); ignoring "
                f"{self._credentials.url!r}",
            )

    def _warn_ignored_rate_limit_overrides(self) -> None:
        from comicbox.config.settings import resolve_rate_limit

        limits = resolve_rate_limit(self._settings, self.name)
        if limits.per_minute is not None or limits.per_day is not None:
            warn_once(
                f"{self.name}:rate-limit-override",
                f"online {self.name}: rate_limit.per_minute/per_day "
                "overrides are ignored — mokkari>=4.0.1 tracks Metron's "
                "actual per-user rate limits from response headers instead "
                "of a fixed local bucket",
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
            url=_bi_resource_url(base_issue),
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
        request, returns ≤1 result on healthy data. The base class's
        ``lookup_issue`` wrapper owns the failure semantics.
        """
        session = self._get_session()
        params: dict[str, Any] = {"series_id": volume_id}
        if number := strip_issue_leading_zeros(issue_number):
            params["number"] = number
        issues = self._issues_list_with_retry(session, params)
        issue_list = list(issues)
        if not issue_list:
            return None
        # On the rare multi-result case (cover variants under one
        # `number`), accept the first — caller would otherwise need to
        # decide between variants which is a different problem.
        return self._to_candidate(issue_list[0], series_id=volume_id)

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
        session = self._get_session()
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
        per search. Metron caps every user at 20 req/min; mokkari tracks
        that from response headers and only pre-empts a request once it
        already knows the window is exhausted (a shared `Session` makes
        that check advisory, not a hard gate — see `Runner._run_parallel`
        in comicbox/run.py), so under -j N batch contention several
        workers' calls can still collide in the same window and raise
        `RateLimitError` with a `retry_after` hint.

        Decorating this method with `@with_retry()` means the retry
        decorator catches that error, honors the server-side
        `retry_after`, sleeps, and replays the single failed call rather
        than spamming "issue-list … failed" warnings and dropping the
        data.
        """
        self._record_api_call("issues_list")
        return session.issues_list(params=params)
