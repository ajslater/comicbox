"""
VerseDB API source via the `versedb` SDK, behind `versedb_api.client`.

A cold comic costs three requests: one series search, one issue list across
every kept series at once, and the detail fetch of the issue accepted.
VerseDB's ``list_issues`` takes many ``series_ids`` in one call, so there is
no per-series fan-out to budget (AJ's call, 2026-11-21: one call, because it
minimizes API usage). Effort therefore moves nothing here, as for Metron.

The free tier allows 300 requests an hour and 4,000 a day. There is no
client-side pacing: a 429's ``Retry-After`` drives `with_retry`'s rate-limit
path, as Comic Vine's hourly cap does, and the adapter refuses to send while
that cooldown runs.

VerseDB candidates carry no precomputed cover hash, so the matcher hashes
the candidate's thumbnail when it needs to.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Any, ClassVar, Final

from loguru import logger

from comicbox.config.online.settings import Effort
from comicbox.events import SKIP_QUOTA_RESERVED
from comicbox.formats import MetadataFormats
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.retry import RetryCategory, with_retry
from comicbox.formats.base.online.series_filter import (
    should_keep_volume_name,
    threshold_for,
)
from comicbox.formats.base.online.sources.base import OnlineSource
from comicbox.formats.base.online.warn_once import warn_once
from comicbox.formats.sources import MetadataSources
from comicbox.formats.versedb_api.cache import open_response_cache
from comicbox.formats.versedb_api.client import (
    VerseDBAuthError,
    VerseDBClient,
    VerseDBNotFoundError,
    VerseDBQuotaError,
    VerseDBRateLimitError,
    VerseDBResponseError,
    VerseDBServerError,
)
from comicbox.formats.versedb_api.transform import (
    issue_url,
    original_format,
    split_issue_number,
)
from comicbox.version import user_agent

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from comicbox.formats.base.online.profile import ComicProfile

# The series-name pre-filter, at the threshold calibrated for Comic Vine's
# balanced effort (zero outcome changes, see `series_filter`). Fixed rather
# than effort-driven: it trims what goes into the one issue-list call, it
# doesn't decide whether a call is made.
_NAME_THRESHOLD: Final = threshold_for(Effort.BALANCED)

# Clients are shared process-wide by credential set, keyed by (token,
# base_url): sources are rebuilt per file, and every file and worker thread
# should reuse one connection pool and one cache handle. FIRST BUILD WINS,
# as for the other two sources; a later source with different cache
# settings is warned once and reuses the built client. A closed client
# can't send, so it is dropped and rebuilt on next use. Only its in-memory
# budget readout and cooldown are lost; the cache file keeps its rows.
_client_cache: dict[tuple[str, str], tuple[VerseDBClient, tuple]] = {}
_client_cache_lock = threading.Lock()


def close_shared_sessions() -> None:
    """Close every shared client's connections and cache handle, and drop it."""
    with _client_cache_lock:
        entries = list(_client_cache.values())
        _client_cache.clear()
    for client, _signature in entries:
        client.close()


def reset_shared_sessions() -> None:
    """Close and drop every shared client. Test seam, as for the other sources."""
    close_shared_sessions()


def shared_client_rate_limit_status(
    token: str | None, base_url: str | None = None
) -> dict[str, dict[str, Any]]:
    """
    Report the hourly budget VerseDB last gave this credential set's client.

    ``{"hour": {"limit", "remaining", "reset_epoch": None}}``, or ``{}`` when
    no shared client exists yet or none of its responses carried the
    headers. VerseDB sends no reset time, so ``reset_epoch`` is always None.
    """
    with _client_cache_lock:
        entry = _client_cache.get((token or "", base_url or ""))
    return entry[0].rate_limit_status() if entry else {}


def _display_text(text: str | None) -> str | None:
    """Trim a free-text display field; blank reads as absent."""
    return (text or "").strip() or None


def _alt_names(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Gather a search row's other names, every language's, deduplicated."""
    aliases = row.get("aliases_i18n") or {}
    names = (name for names in aliases.values() for name in names or () if name)
    return tuple(dict.fromkeys(names))


def _number_matches(row: Mapping[str, Any], number: str | None) -> bool:
    """
    Whether an issue row has exactly the comic's number.

    The server's ``q`` matches loosely (a prefix: "1" finds 10 to 19, and
    names), so this is what keeps the candidates honest. A dual-numbered row
    such as "1 [10]" matches on the number before the bracket.
    """
    if number is None:
        return True
    raw, _alt = split_issue_number(row.get("issue_number"))
    return (strip_issue_leading_zeros(raw) or "").casefold() == number.casefold()


class VerseDBOnlineSource(OnlineSource):
    """Wraps the `versedb` SDK adapter for VerseDB's API."""

    name: ClassVar[str] = "versedb"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.VERSEDB_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.VERSEDB_API

    #: Test seam: an `httpx.MockTransport` every new client sends through.
    http_transport: ClassVar[Any] = None

    # How many series one search asks for, all of which can go into the one
    # issue-list call.
    _MAX_SERIES_PER_SEARCH: ClassVar[int] = 20
    # Exact matches rank first in VerseDB's issue list (seen 2026-11-21), so
    # a next page is fetched only while a page still ends in one, and never
    # past this many.
    _MAX_ISSUE_PAGES: ClassVar[int] = 3
    # A series that began more than this many years after the comic can't
    # hold it; it would be a reprint run carrying the original's date. The
    # slop matches the matcher's one-year tolerance.
    _SERIES_START_YEAR_SLOP: ClassVar[int] = 1

    @override
    def is_configured(self) -> bool:
        """VerseDB requires a personal access token."""
        return bool(self._credentials.key)

    @override
    @staticmethod
    def classify_retry_exception(exc: BaseException) -> RetryCategory | None:
        """
        Classify the adapter's exceptions, and httpx's transport failures.

        Every `VerseDBError` subclass is claimed here: an unclaimed vendor
        exception would be silently retried on the generic schedule.
        """
        import httpx

        categories: tuple[tuple[type[BaseException], RetryCategory], ...] = (
            (VerseDBQuotaError, RetryCategory.QUOTA),
            (VerseDBRateLimitError, RetryCategory.RATE_LIMIT),
            (VerseDBAuthError, RetryCategory.AUTH),
            (VerseDBNotFoundError, RetryCategory.NOT_FOUND),
            (VerseDBServerError, RetryCategory.TRANSIENT),
            # An unexpected status or an unparsable response: the same
            # request can only fail the same way.
            (VerseDBResponseError, RetryCategory.INVALID),
            (httpx.TimeoutException, RetryCategory.TRANSIENT),
            (httpx.TransportError, RetryCategory.TRANSIENT),
        )
        for exc_class, category in categories:
            if isinstance(exc, exc_class):
                return category
        return None

    # -- the shared client --------------------------------------------------

    def _get_client(self) -> VerseDBClient:
        if self._client is None or self._client.closed:
            self._client = self._get_or_build_shared_client()
        return self._client

    def _client_signature(self) -> tuple:
        cache = self._settings.cache
        return (cache.mode, cache.dir, cache.ttl)

    def _get_or_build_shared_client(self) -> VerseDBClient:
        key = (self._credentials.key or "", self._credentials.url or "")
        signature = self._client_signature()
        with _client_cache_lock:
            entry = _client_cache.get(key)
            if entry is None or entry[0].closed:
                client = self._build_client()
                _client_cache[key] = (client, signature)
                return client
        client, built_signature = entry
        if built_signature != signature:
            warn_once(
                f"{self.name}:session-config-mismatch",
                f"online {self.name}: reusing the existing shared client; this "
                f"instance's differing cache settings {signature} are ignored "
                f"in favor of the client's {built_signature}",
            )
        return client

    def _build_client(self, *, cached: bool = True) -> VerseDBClient:
        cache = None
        if cached and (resolved := self._resolve_response_cache()) is not None:
            path, ttl = resolved
            cache = open_response_cache(path, ttl)
        return VerseDBClient(
            self._credentials.key or "",
            user_agent=user_agent(),
            base_url=self._credentials.url,
            cache=cache,
            transport=self.http_transport,
        )

    @override
    def probe(self) -> Mapping[str, Mapping[str, Any]] | None:
        """Verify the token with one uncached one-row series request."""
        client = self._build_client(cached=False)
        try:
            self._record_api_call("probe")
            return client.probe()
        finally:
            client.close()

    # -- fetch and search ---------------------------------------------------

    @override
    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """
        Fetch one issue's full detail.

        One request: the detail already nests the series, publisher, credits
        and the rest, so nothing needs a second call.
        """
        self._record_api_call("get_issue")
        payload = self._get_client().issue(issue_id)
        data = payload.get("data")
        if not isinstance(data, dict):
            reason = f"VerseDB issue {issue_id}: the response carries no data"
            raise VerseDBResponseError(reason)
        return data

    @override
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search VerseDB for candidate issues matching the profile.

        1. ``--series-id versedb:<id>`` skips discovery.
        2. One series search by name.
        3. Drop a series that began after the comic, or whose name (and
           other names) is too far from the comic's series.
        4. One issue list across all the kept series, filtered client-side
           to the comic's exact number.

        While VerseDB refuses requests for longer than any retry waits (its
        daily cap), nothing is sent: the comic is reported skipped, so it is
        tried again on a later run, and the run's other sources carry on.
        """
        self.reset_search_skip_reason()
        try:
            return self._search(profile)
        except VerseDBQuotaError:
            self._note_search_skipped(SKIP_QUOTA_RESERVED)
            return []

    def _search(self, profile: ComicProfile) -> list[Candidate]:
        number = strip_issue_leading_zeros(profile.issue)
        explicit_sid = self._settings.lookup.series_ids.get(self.name)
        if explicit_sid is not None:
            return self._issues_in_series({int(explicit_sid): ()}, number)
        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search "
                "(use --id versedb:<id>, or --series-id versedb:<id>)"
            )
            return []
        rows = self._search_series_with_retry(profile.series)
        self._log_discovery_sample(
            rows,
            lambda row: (
                f"{row.get('display_name') or row.get('name')} ({row.get('id')})"
            ),
            noun="series",
            query=f"series={profile.series!r}",
        )
        kept = self._kept_series(rows, profile)
        if not kept:
            logger.info(
                f"online {self.name}: no series match series {profile.series!r}"
            )
            return []
        return self._issues_in_series(kept, number)

    @override
    def _lookup_issue_in_volume(
        self, volume_id: int, issue_number: str | None
    ) -> Candidate | None:
        """
        Take the series-cache fast path: one issue list in one series.

        Returns None without a request when there is no issue number: the
        whole series would come back and its first row would win.
        """
        number = strip_issue_leading_zeros(issue_number)
        if not number:
            return None
        try:
            candidates = self._issues_in_series({int(volume_id): ()}, number)
        except VerseDBQuotaError:
            # Quietly: the search this falls back to reports the skip.
            return None
        # First-result-wins on variant collisions, as for the other sources.
        return candidates[0] if candidates else None

    def _series_postdates_comic(self, start_year: Any, year: int | None) -> bool:
        if start_year is None or year is None:
            return False
        return int(start_year) > year + self._SERIES_START_YEAR_SLOP

    def _kept_series(
        self, rows: Sequence[Mapping[str, Any]], profile: ComicProfile
    ) -> dict[int, tuple[str, ...]]:
        """Each surviving series id, with the other names its row carried."""
        kept: dict[int, tuple[str, ...]] = {}
        for row in rows:
            if (series_id := row.get("id")) is None:
                continue
            name = row.get("name")
            if self._series_postdates_comic(row.get("start_year"), profile.year):
                logger.debug(
                    f"online {self.name}: skipping series {series_id} ({name!r}, "
                    f"start_year={row.get('start_year')}); comic year="
                    f"{profile.year} predates it."
                )
                continue
            alt_names = _alt_names(row)
            if not should_keep_volume_name(
                profile.series, name, _NAME_THRESHOLD, alt_names=alt_names
            ):
                logger.debug(
                    f"online {self.name}: skipping series {series_id} ({name!r}); "
                    f"name dissimilar to profile.series={profile.series!r}."
                )
                continue
            kept[int(series_id)] = alt_names
        return kept

    def _issues_in_series(
        self, alt_names_by_id: Mapping[int, tuple[str, ...]], number: str | None
    ) -> list[Candidate]:
        """Candidates for ``number`` across these series, in as few calls as can be."""
        series_ids = tuple(alt_names_by_id)
        candidates: list[Candidate] = []
        for page in range(1, self._MAX_ISSUE_PAGES + 1):
            payload = self._list_issues_with_retry(series_ids, number, page)
            rows = payload.get("data") or []
            candidates.extend(
                self._to_candidate(row, alt_names_by_id.get(row.get("series_id"), ()))
                for row in rows
                if row.get("id") is not None and _number_matches(row, number)
            )
            if not self._next_page_may_match(payload, rows, number, page):
                break
        return candidates

    @staticmethod
    def _next_page_may_match(
        payload: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        number: str | None,
        page: int,
    ) -> bool:
        """
        Whether another page could still hold exact matches.

        Exact matches rank first, so a page that ends in a non-match means
        the rest are non-matches too. Without a number every row matches,
        and one page is all a numberless comic gets.
        """
        last_page = (payload.get("meta") or {}).get("last_page") or 1
        return bool(
            number is not None
            and rows
            and page < last_page
            and _number_matches(rows[-1], number)
        )

    @with_retry()
    def _search_series_with_retry(self, name: str) -> list[dict[str, Any]]:
        self._record_api_call("search_series")
        payload = self._get_client().search_series(name, self._MAX_SERIES_PER_SEARCH)
        return payload.get("data") or []

    @with_retry()
    def _list_issues_with_retry(
        self, series_ids: Sequence[int], number: str | None, page: int
    ) -> dict[str, Any]:
        self._record_api_call("list_issues")
        return self._get_client().list_issues(series_ids, number, page=page)

    def _to_candidate(
        self, row: Mapping[str, Any], alt_series: tuple[str, ...]
    ) -> Candidate:
        """
        Map an issue-list row, with its included series, to a Candidate.

        ``publisher`` stays None as for the other sources: `s_publisher`
        scores it, and filling it would move scores no calibration has
        measured. The series' publisher is shown as display detail instead.
        """
        series = row.get("series") or {}
        images = row.get("images") or {}
        publisher = _display_text(series.get("publisher_name"))
        summary = CandidateSummary(
            series=series.get("name") or "",
            issue=str(row.get("issue_number") or ""),
            year=parse_year(row.get("cover_date") or row.get("release_date")),
            publisher=None,
            page_count=None,
            cover_url=images.get("thumb")
            or images.get("cover_sm")
            or row.get("cover_url"),
            variant_label=None,
            alt_series=alt_series,
            volume=series.get("volume_number"),
            cover_url_full=images.get("cover_lg"),
            series_start_year=series.get("start_year"),
            series_publisher=publisher,
            series_issue_count=series.get("cached_issues_count") or None,
            series_type=original_format(series),
            issue_title=_display_text(row.get("name")),
        )
        return Candidate(
            source=self.name,
            issue_id=int(row["id"]),
            summary=summary,
            url=issue_url(row.get("id"), row.get("slug")) or "",
            precomputed_cover_hash=None,
            volume_id=row.get("series_id"),
        )
