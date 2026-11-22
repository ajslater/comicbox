"""
The `versedb` SDK adapter: the only module in comicbox that imports `versedb`.

The SDK is generated code (openapi-python-client). It ships no rate limiter,
no response cache and no retry, and it reports errors as return values. Its
function names come from endpoint summaries and can change when it is
regenerated. So the rest of comicbox sees only this module: plain dicts of
the server's own JSON and the comicbox exceptions below. A renamed SDK
function touches this file alone, and its internals could be swapped for raw
httpx without changing anything else.

What this adds on top of the SDK:

- One `httpx.Client`, built eagerly. The SDK builds it lazily and mutates its
  own headers first, which races across worker threads.
- Responses mapped by HTTP status, never by SDK model class.
- A guard for the SDK's strict parsing. A missing key, or a non-JSON error
  body, raises inside the SDK before it returns, losing the status. A
  response hook records each status first, so a failed parse can still be
  mapped by it.
- The optional response cache (`versedb_api.cache`): 200s only, and never
  one marked ``no-store``.
- A 429 cooldown: until the server's ``Retry-After`` has passed, every call
  fails at once without sending, so N workers don't each spend a request to
  learn the same thing. A wait longer than the retry layer will ever do (a
  daily cap) is a `VerseDBQuotaError`, never retried: VerseDB is not asked
  again until it lapses, and the run's other sources carry on.
- The hourly budget from ``X-RateLimit-*``, for the doctor and Codex.

`versedb` is imported inside functions only: its endpoint modules load all
1,011 of its model modules, about 0.8 s, so the exception classes here can be
imported without paying for it.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NoReturn

from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.retry import MAX_RATE_LIMIT_WAIT_S
from comicbox.formats.base.online.warn_once import warn_once

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import httpx

    from comicbox.formats.versedb_api.cache import ResponseCache

SOURCE_NAME: Final = "versedb"
DEFAULT_BASE_URL: Final = "https://versedb.com"
# The SDK's default falls back to httpx's 5 seconds; comicbox's own cover
# client uses 15.
_TIMEOUT_S: Final = 15.0
# How long to refuse requests after a 429 that named no Retry-After. Matches
# the first step of the retry layer's rate-limit schedule.
_DEFAULT_COOLDOWN_S: Final = 30.0
# Server-side page caps.
MAX_SERIES_PER_PAGE: Final = 50
MAX_ISSUES_PER_PAGE: Final = 100

_HEADER_LIMIT: Final = "x-ratelimit-limit"
_HEADER_REMAINING: Final = "x-ratelimit-remaining"
_HOUR_WINDOW: Final = "hour"
# An empty answer is kept for a day, whatever the cache's ttl, as Metron's
# are: an issue VerseDB adds tomorrow should be found tomorrow. AJ asked to
# cache as much as possible; this is still caching, and spends at most one
# request a day per empty question.
EMPTY_RESULT_TTL: Final = timedelta(days=1)
_OK: Final = 200
_UNAUTHORIZED: Final = 401
_FORBIDDEN: Final = 403
_NOT_FOUND: Final = 404
_TOO_MANY_REQUESTS: Final = 429
_SERVER_ERROR: Final = 500


class VerseDBError(Exception):
    """Base class for every failure the adapter reports."""


class VerseDBAuthError(VerseDBError):
    """
    HTTP 401 or 403: the request was refused, and retrying won't change that.

    A 401 is a missing or wrong token. A 403 is a token without a scope the
    request needs, or, when it carries no ``X-RateLimit-*`` headers,
    something in front of VerseDB's API refusing it (it sits behind
    Cloudflare).
    """


class VerseDBNotFoundError(VerseDBError):
    """HTTP 404: no such issue."""


class VerseDBRateLimitError(VerseDBError):
    """
    HTTP 429, or a call refused while a 429's cooldown runs.

    ``retry_after`` is the seconds the server asked for, read by
    `retry._retry_after`; None when it named none.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Keep the server's hint for the retry layer."""
        super().__init__(message)
        self.retry_after = retry_after


class VerseDBQuotaError(VerseDBError):
    """
    VerseDB refuses requests for longer than comicbox ever waits.

    A 429 whose ``Retry-After`` is past `retry.MAX_RATE_LIMIT_WAIT_S`, most
    likely the free tier's 4,000-a-day cap. Retrying would only sleep out the
    ceiling and be refused again, so this is never retried, and the client
    sends nothing more until ``resume_at`` (epoch seconds).
    """

    def __init__(self, message: str, resume_at: float) -> None:
        """Keep when VerseDB said to come back."""
        super().__init__(message)
        self.resume_at = resume_at


class VerseDBServerError(VerseDBError):
    """HTTP 5xx."""


class VerseDBResponseError(VerseDBError):
    """Any other status, or a response the `versedb` package could not parse."""


def _endpoints() -> MappingProxyType[str, Any]:
    """
    Map comicbox's own name for each SDK function it calls to the function.

    The keyword parameters used are pinned by a drift test, so an SDK
    regeneration that renames one fails at dependency-update time.
    """
    from versedb.api.issues import get_issue_details, list_issues
    from versedb.api.series import list_series

    return MappingProxyType(
        {"series": list_series, "issues": list_issues, "issue": get_issue_details}
    )


def _header_int(headers: Mapping[str, str], name: str) -> int | None:
    try:
        return int(headers[name])
    except (KeyError, TypeError, ValueError):
        return None


def _retry_after(headers: Mapping[str, str] | None) -> float | None:
    """Seconds from a 429's ``Retry-After``; None when absent or not a number."""
    if headers is None:
        return None
    try:
        value = float(headers.get("retry-after") or "")
    except ValueError:
        return None
    return value if value > 0 else None


def _storable(headers: Mapping[str, str]) -> bool:
    """
    Whether the terms' "respect cache headers" allows keeping a response.

    VerseDB sends ``no-cache, private`` on everything, Laravel's default when
    an app sets nothing; ``private`` permits a per-user cache, and AJ chose
    (2026-11-21) to cache as much as possible. Only ``no-store`` is refused.
    """
    return "no-store" not in (headers.get("cache-control") or "").lower()


def _endpoint_name(path: str) -> str:
    """
    Name the endpoint a request path addresses, for the run's request counts.

    ``/api/v1/issues`` is a list and ``/api/v1/issues/1234`` a detail fetch:
    distinct names, but one per endpoint rather than one per issue. Named as
    Metron's `endpoint_from_url` names them.
    """
    parts = [part for part in path.split("/") if part]
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
    if not parts:
        return "other"
    is_detail = len(parts) > 1 and parts[1].isdigit()
    return parts[0] if is_detail else f"{parts[0]}_list"


def _quota_message(wait_s: float) -> str:
    resume = datetime.now().astimezone() + timedelta(seconds=wait_s)
    return (
        f"VerseDB's request limit is reached; comicbox won't ask it again until "
        f"about {resume:%H:%M} ({wait_s / 3600:.1f}h)"
    )


def _cache_key(
    base_url: str, endpoint: str, args: Sequence[Any], params: Mapping[str, Any]
) -> str:
    """
    Key a request by everything its answer depends on but the token.

    Every credential set shares one cache file, so the base url is part of
    the key; the token never is.
    """
    request = json.dumps([list(args), dict(params)], sort_keys=True)
    return f"{base_url} {endpoint}:{request}"


def _is_empty(payload: Mapping[str, Any]) -> bool:
    """Whether a list answer found nothing."""
    data = payload.get("data")
    return isinstance(data, list) and not data


def _has_rate_limit_headers(headers: Mapping[str, str] | None) -> bool:
    return bool(headers) and _header_int(headers or {}, _HEADER_LIMIT) is not None


class VerseDBClient:
    """
    VerseDB's API as plain dicts and comicbox exceptions.

    Thread-safe: one instance is shared by every worker of a run.
    """

    def __init__(
        self,
        token: str,
        *,
        user_agent: str,
        base_url: str | None = None,
        cache: ResponseCache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Build the SDK client and its `httpx.Client` now, not lazily."""
        import httpx
        from versedb import AuthenticatedClient

        self._endpoints = _endpoints()
        self._base_url = base_url or DEFAULT_BASE_URL
        self._cache = cache
        self._lock = threading.Lock()
        self._local = threading.local()
        self._cooldown_until = 0.0
        self._window: dict[str, int] = {}
        self._closed = False
        httpx_args: dict[str, Any] = {"event_hooks": {"response": [self._observe]}}
        if transport is not None:
            httpx_args["transport"] = transport
        self._sdk = AuthenticatedClient(
            base_url=self._base_url,
            token=token,
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(_TIMEOUT_S),
            httpx_args=httpx_args,
        )
        self._sdk.get_httpx_client()

    # -- public calls -------------------------------------------------------

    def search_series(self, name: str, limit: int) -> dict[str, Any]:
        """One page of series whose name matches ``name``, best first."""
        limit = max(1, min(limit, MAX_SERIES_PER_PAGE))
        return self._request("series", q=name, limit=limit)

    def list_issues(
        self,
        series_ids: Sequence[int],
        number: str | None = None,
        *,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        One page of issues across several series, each row with its series.

        ``number`` goes to the server's ``q``, which matches loosely: the
        number's prefix, the issue's name, the series name and the slug. The
        caller filters for the exact number.
        """
        params: dict[str, Any] = {
            # Sorted so the same series set is one cache entry, whatever
            # order the search found them in.
            "series_ids": ",".join(str(sid) for sid in sorted(set(series_ids))),
            "include": "series",
            "limit": MAX_ISSUES_PER_PAGE,
            "page": page,
        }
        if number:
            params["q"] = number
        return self._request("issues", **params)

    def issue(self, issue_id: int) -> dict[str, Any]:
        """Fetch the full detail of one issue."""
        return self._request("issue", int(issue_id))

    def probe(self) -> dict[str, dict[str, Any]]:
        """Send the cheapest request, uncached, and return the budget it left."""
        self._request("series", limit=1, use_cache=False)
        return self.rate_limit_status()

    def rate_limit_status(self) -> dict[str, dict[str, Any]]:
        """
        Report the hourly budget the last response carried, as the doctor reads it.

        ``{"hour": {"limit", "remaining", "reset_epoch"}}``, or ``{}`` before
        any response carried the headers. VerseDB sends no reset time.
        """
        with self._lock:
            if not self._window:
                return {}
            return {_HOUR_WINDOW: {**self._window, "reset_epoch": None}}

    @property
    def closed(self) -> bool:
        """Whether `close` has run; a closed client cannot send."""
        return self._closed

    def close(self) -> None:
        """Close the connection pool and the cache. Safe to call twice."""
        self._closed = True
        self._sdk.get_httpx_client().close()
        if self._cache is not None:
            self._cache.close()

    # -- the one request path -----------------------------------------------

    def _request(
        self, endpoint: str, *args: Any, use_cache: bool = True, **params: Any
    ) -> dict[str, Any]:
        import httpx

        cache = self._cache if use_cache else None
        key = _cache_key(self._base_url, endpoint, args, params)
        if cache is not None and (payload := _cached_payload(cache, key)) is not None:
            return payload
        self._refuse_while_cooling_down()
        func = self._endpoints[endpoint]
        self._local.status = None
        self._local.headers = None
        try:
            response = func.sync_detailed(*args, client=self._sdk, **params)
        except httpx.TransportError:
            # No response at all: a timeout, a refused connection, or a
            # firewall dropping the address, which nothing else here shows.
            outcome_stats.record_connection_failure(SOURCE_NAME)
            raise
        except (KeyError, TypeError, ValueError) as exc:
            self._raise_for_parse_failure(endpoint, exc)
        status = int(response.status_code)
        if status != _OK:
            self._raise_for_status(endpoint, status, response.headers)
        payload = json.loads(response.content)
        if cache is not None and _storable(response.headers):
            max_ttl = EMPTY_RESULT_TTL if _is_empty(payload) else None
            cache.set(key, response.content, max_ttl=max_ttl)
        return payload

    def _raise_for_parse_failure(self, endpoint: str, exc: Exception) -> NoReturn:
        """Map a failed SDK parse by the status the hook saw, if it saw one."""
        status = getattr(self._local, "status", None)
        if status is not None and status != _OK:
            self._raise_for_status(endpoint, status, self._local.headers)
        reason = (
            f"VerseDB {endpoint}: the response did not parse "
            f"({type(exc).__name__}: {exc}); the versedb package may be "
            "behind the API"
        )
        raise VerseDBResponseError(reason) from exc

    def _raise_for_status(
        self, endpoint: str, status: int, headers: Mapping[str, str] | None
    ) -> NoReturn:
        prefix = f"VerseDB {endpoint}: HTTP {status}"
        if status == _UNAUTHORIZED:
            reason = f"{prefix}: check the API token"
            raise VerseDBAuthError(reason)
        if status == _FORBIDDEN:
            if _has_rate_limit_headers(headers):
                reason = f"{prefix}: the token may lack a scope this request needs"
            else:
                reason = (
                    f"{prefix}: refused before it reached VerseDB's API, by a "
                    "proxy or bot check, or the token lacks a scope it needs"
                )
            raise VerseDBAuthError(reason)
        if status == _NOT_FOUND:
            raise VerseDBNotFoundError(prefix)
        if status == _TOO_MANY_REQUESTS:
            retry_after = _retry_after(headers)
            self._start_cooldown(retry_after)
            if retry_after is not None and retry_after > MAX_RATE_LIMIT_WAIT_S:
                self._raise_quota(retry_after)
            reason = f"{prefix}: rate limited"
            raise VerseDBRateLimitError(reason, retry_after)
        if status >= _SERVER_ERROR:
            raise VerseDBServerError(prefix)
        raise VerseDBResponseError(prefix)

    # -- rate-limit state ---------------------------------------------------

    def _start_cooldown(self, retry_after: float | None) -> None:
        until = time.monotonic() + (retry_after or _DEFAULT_COOLDOWN_S)
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, until)

    def _refuse_while_cooling_down(self) -> None:
        with self._lock:
            remaining = self._cooldown_until - time.monotonic()
        if remaining > MAX_RATE_LIMIT_WAIT_S:
            self._raise_quota(remaining)
        if remaining > 0:
            reason = f"VerseDB: rate limited; not sending for another {remaining:.0f}s"
            raise VerseDBRateLimitError(reason, remaining)

    @staticmethod
    def _raise_quota(wait_s: float) -> NoReturn:
        """
        Stop asking VerseDB until a wait longer than any retry has passed.

        Said once, plainly; every later refusal carries the same words but
        stays quiet, and the sources that still have budget carry on.
        """
        message = _quota_message(wait_s)
        warn_once(
            f"{SOURCE_NAME}:quota",
            f"online {SOURCE_NAME}: {message}. Other online sources carry on; a "
            "re-run after that tags what VerseDB skipped.",
        )
        raise VerseDBQuotaError(message, time.time() + wait_s)

    def _observe(self, response: httpx.Response) -> None:
        """
        Record one response's status and budget before the SDK parses it.

        An httpx response hook: it runs on the thread that sent the request,
        so the status it keeps in thread-local storage is that request's.
        """
        status = response.status_code
        headers = response.headers
        self._local.status = status
        self._local.headers = headers
        outcome_stats.record_http_request(
            SOURCE_NAME, _endpoint_name(response.request.url.path)
        )
        if status == _TOO_MANY_REQUESTS:
            outcome_stats.record_rate_limit_rejection(SOURCE_NAME)
        limit = _header_int(headers, _HEADER_LIMIT)
        remaining = _header_int(headers, _HEADER_REMAINING)
        if limit is None or remaining is None:
            self._report_unthrottled(status)
            return
        with self._lock:
            self._window = {"limit": limit, "remaining": remaining}

    @staticmethod
    def _report_unthrottled(status: int) -> None:
        """
        Count a response with no ``X-RateLimit-*`` headers.

        VerseDB puts them on its 200s and 404s. Only a 401 is left out: an
        unauthenticated request carries none, and that is the token's fault.
        A bare 403 is counted, because a CDN or bot check in front of the API
        refuses that way too, and the doctor's warning for it should fire.
        """
        if status == _UNAUTHORIZED:
            return
        outcome_stats.record_unthrottled_response(SOURCE_NAME, status)
        warn_once(
            f"{SOURCE_NAME}:no-rate-limit-headers",
            f"{SOURCE_NAME}: a response arrived with no X-RateLimit-* headers "
            f"(status {status}); VerseDB's API sends them, so this one came "
            "from something in front of it.",
        )


def _cached_payload(cache: ResponseCache, key: str) -> dict[str, Any] | None:
    """Return a cached response, parsed; a body that won't parse is a miss."""
    if (body := cache.get(key)) is None:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def endpoint_keywords() -> dict[str, frozenset[str]]:
    """
    List the keyword parameters of each SDK function, for the drift test.

    Imports the SDK; call it from tests only.
    """
    import inspect

    return {
        name: frozenset(inspect.signature(func.sync_detailed).parameters)
        for name, func in _endpoints().items()
    }


#: The keyword parameters comicbox passes to each SDK function.
USED_KEYWORDS: Final[MappingProxyType[str, frozenset[str]]] = MappingProxyType(
    {
        "series": frozenset({"client", "q", "limit"}),
        "issues": frozenset({"client", "series_ids", "include", "limit", "page", "q"}),
        "issue": frozenset({"client", "issue_id"}),
    }
)
