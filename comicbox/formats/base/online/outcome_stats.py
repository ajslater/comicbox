"""
End-of-run outcome counters for online tagging.

Tracks how many comics fell into each match-resolution bucket across a
run so the runner can print a summary like:

  Online tagging summary:
    16 auto-written
     2 prompted (chose 1, declined 1)
     3 skipped
     1 no-match

Process-wide singleton; reset at the start of each `Runner.run()`.
Thread-safe so `-j N` parallel batches contribute correctly.

Only the CLI prints any of this: `Runner.run()` is the sole caller of
`summary_lines()`. An embedding application (codex) logs its own spend,
so a counter an embedder needs has to be readable from `api_snapshot()`
rather than waited for in a summary that is never printed there.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace


@dataclass
class _ApiCounts:
    """
    HTTP-level cost of one source, alongside its outcome counts.

    Distinct from ``OnlineSource.api_call_counts``, which counts calls at
    comicbox's wrapper level: that number includes response-cache hits and
    counts a paginated result as one. ``requests`` counts responses
    RECEIVED, per endpoint, recorded where the raw response arrives, so
    the number a user pastes into a bug report lines up with the server's
    own logs. A send that never answered is counted only in
    ``connection_failures``.
    """

    requests: dict[str, int] = field(default_factory=dict)
    rejections: int = 0
    blocked_seconds: float = 0.0
    # Responses that carried no `X-RateLimit-*` header at all, by HTTP
    # status. A genuine Metron `/api/` response of ANY status carries
    # them: DRF runs its throttles in `initial()`, before any view code,
    # before the conditional GET's 304 and before `X-Cache`. So their
    # absence proves the answer came from something in front of Django
    # rather than from the API, and bucketing by status catches an Anubis
    # challenge page (served as HTTP 200 HTML) as readily as a 429.
    unthrottled: dict[int, int] = field(default_factory=dict)
    # Sends that never produced a response: mokkari wraps `requests`
    # ConnectionError and ReadTimeout in `ApiError`. This is the shape a
    # firewall-level ban takes, where the client only ever sees timeouts.
    connection_failures: int = 0
    burst_limit: int | None = None
    burst_remaining: int | None = None
    sustained_limit: int | None = None
    sustained_remaining: int | None = None


@dataclass
class _Counts:
    auto_write: int = 0
    prompt_accepted: int = 0
    prompt_declined: int = 0
    skip: int = 0
    no_match: int = 0
    # Direct id-fetch path (`--id <db>:<n>`); not technically a resolution
    # outcome but worth distinguishing in the summary.
    explicit_id: int = 0


class _OutcomeStats:
    """Process-wide thread-safe outcome counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = _Counts()
        self._per_source: dict[str, _Counts] = {}
        self._per_source_api: dict[str, _ApiCounts] = {}

    def reset(self) -> None:
        """Clear all counters (called at the start of each Runner.run())."""
        with self._lock:
            self._counts = _Counts()
            self._per_source = {}
            self._per_source_api = {}

    def _bucket_for(self, source_name: str) -> _Counts:
        """Get-or-create the per-source bucket. Caller must hold `_lock`."""
        bucket = self._per_source.get(source_name)
        if bucket is None:
            bucket = _Counts()
            self._per_source[source_name] = bucket
        return bucket

    def record_auto_write(self, source_name: str) -> None:
        """Record an auto-written candidate (no prompt)."""
        with self._lock:
            self._counts.auto_write += 1
            self._bucket_for(source_name).auto_write += 1

    def record_prompt_accepted(self, source_name: str) -> None:
        """Record a candidate picked from a user prompt."""
        with self._lock:
            self._counts.prompt_accepted += 1
            self._bucket_for(source_name).prompt_accepted += 1

    def record_prompt_declined(self, source_name: str) -> None:
        """Record a user declining the prompt (no candidate selected)."""
        with self._lock:
            self._counts.prompt_declined += 1
            self._bucket_for(source_name).prompt_declined += 1

    def record_skip(self, source_name: str) -> None:
        """Record a SKIP (matcher declined under `--prompts never`)."""
        with self._lock:
            self._counts.skip += 1
            self._bucket_for(source_name).skip += 1

    def record_no_match(self, source_name: str) -> None:
        """Record a NO_MATCH (no candidate cleared `min_confidence`)."""
        with self._lock:
            self._counts.no_match += 1
            self._bucket_for(source_name).no_match += 1

    def record_explicit_id(self, source_name: str) -> None:
        """Record a direct `--id <db>:<n>` fetch (bypasses resolution)."""
        with self._lock:
            self._counts.explicit_id += 1
            self._bucket_for(source_name).explicit_id += 1

    def _api_bucket_for(self, source_name: str) -> _ApiCounts:
        """Get-or-create the per-source API bucket. Caller must hold `_lock`."""
        bucket = self._per_source_api.get(source_name)
        if bucket is None:
            bucket = _ApiCounts()
            self._per_source_api[source_name] = bucket
        return bucket

    def record_http_request(self, source_name: str, endpoint: str) -> None:
        """Record one response received, by endpoint."""
        with self._lock:
            bucket = self._api_bucket_for(source_name)
            bucket.requests[endpoint] = bucket.requests.get(endpoint, 0) + 1

    def record_gate_wait(self, source_name: str, seconds: float) -> None:
        """Record what one send waited at the rate gate before going out."""
        with self._lock:
            self._api_bucket_for(source_name).blocked_seconds += seconds

    def record_rate_limit_rejection(self, source_name: str) -> None:
        """Record one server rate-limit rejection (a 429 we still paid for)."""
        with self._lock:
            self._api_bucket_for(source_name).rejections += 1

    def record_unthrottled_response(self, source_name: str, status: int) -> None:
        """Record a response that carried no rate-limit headers, by status."""
        with self._lock:
            bucket = self._api_bucket_for(source_name)
            bucket.unthrottled[status] = bucket.unthrottled.get(status, 0) + 1

    def record_connection_failure(self, source_name: str) -> None:
        """Record a send that never produced a response (transport failure)."""
        with self._lock:
            self._api_bucket_for(source_name).connection_failures += 1

    def record_rate_limit_windows(
        self,
        source_name: str,
        *,
        burst_limit: int | None = None,
        burst_remaining: int | None = None,
        sustained_limit: int | None = None,
        sustained_remaining: int | None = None,
    ) -> None:
        """Record the latest rate-limit window figures the server reported."""
        with self._lock:
            bucket = self._api_bucket_for(source_name)
            if burst_limit is not None:
                bucket.burst_limit = burst_limit
            if burst_remaining is not None:
                bucket.burst_remaining = burst_remaining
            if sustained_limit is not None:
                bucket.sustained_limit = sustained_limit
            if sustained_remaining is not None:
                bucket.sustained_remaining = sustained_remaining

    def api_snapshot(self) -> dict[str, _ApiCounts]:
        """Return a consistent copy of the per-source HTTP counters."""
        with self._lock:
            return {k: _copy_api(v) for k, v in self._per_source_api.items()}

    def has_any_activity(self) -> bool:
        """Return True if any outcome was recorded since last reset."""
        with self._lock:
            return _has_any(self._counts) or bool(self._per_source_api)

    def summary_lines(self) -> list[str]:
        """Format the end-of-run summary as a list of log lines."""
        with self._lock:
            has_outcomes = _has_any(self._counts)
            if not has_outcomes and not self._per_source_api:
                return []
            counts_snapshot = _Counts(**self._counts.__dict__)
            per_source_snapshot = {
                k: _Counts(**v.__dict__) for k, v in self._per_source.items()
            }
            api_snapshot = {k: _copy_api(v) for k, v in self._per_source_api.items()}
        lines = (
            _format_summary(counts_snapshot, per_source_snapshot)
            if has_outcomes
            else []
        )
        lines.extend(_format_api_lines(api_snapshot))
        return lines


def _copy_api(c: _ApiCounts) -> _ApiCounts:
    """Deep-enough copy: the only mutable members are the count maps."""
    return replace(c, requests=dict(c.requests), unthrottled=dict(c.unthrottled))


def _format_api_lines(per_source: dict[str, _ApiCounts]) -> list[str]:
    """
    Format the HTTP-cost block appended to the outcome summary.

    Written so a user can paste it into a bug report and have the numbers
    line up with what the server logged: total sends, how they split by
    endpoint, how many the server refused, how long pacing cost, and where
    the quota stands at the end of the run.
    """
    lines: list[str] = []
    for src in sorted(per_source):
        lines.extend(_format_source_api_lines(src, per_source[src]))
    return lines


def _format_source_api_lines(src: str, api: _ApiCounts) -> list[str]:
    """Format one source's block: the header row and whichever rows apply."""
    total = sum(api.requests.values())
    if not total and not api.rejections:
        return []
    breakdown = ", ".join(
        f"{count} {endpoint}" for endpoint, count in sorted(api.requests.items())
    )
    rows = (_format_detail(api), _format_unthrottled(api), _format_budget_row(api))
    lines = [f"  {src} API: {total} requests ({breakdown})"]
    lines.extend(f"    {row}" for row in rows if row)
    return lines


def _format_detail(api: _ApiCounts) -> str:
    """Summarize what the server refused, what never arrived, and pacing cost."""
    detail: list[str] = []
    if api.rejections:
        detail.append(f"{api.rejections} rate-limited")
    if api.connection_failures:
        detail.append(_plural(api.connection_failures, "connection failure"))
    if api.blocked_seconds >= 1.0:
        detail.append(f"{api.blocked_seconds:.0f}s paced")
    return ", ".join(detail)


def _format_budget_row(api: _ApiCounts) -> str:
    """Where the quota stands, or nothing when the server never said."""
    budget = _format_budget(api)
    return f"remaining: {budget}" if budget else ""


def _plural(count: int, noun: str) -> str:
    """Render `count noun` with a naive plural, for summary prose."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _format_unthrottled(api: _ApiCounts) -> str:
    """
    Report responses that arrived with no rate-limit headers, by status.

    Deliberately not "429s without headers": a header-less response of
    any status is the interesting event, because it did not come from
    Metron's API layer at all. Counting every status catches a proxy
    error page and a bot-check challenge — which are served as HTTP 200 —
    without inspecting a single response body.
    """
    if not api.unthrottled:
        return ""
    total = sum(api.unthrottled.values())
    by_status = ", ".join(
        f"{status}: {count}" for status, count in sorted(api.unthrottled.items())
    )
    return f"{_plural(total, 'response')} without rate-limit headers ({by_status})"


def _format_budget(api: _ApiCounts) -> str:
    """Render whatever of the two rate-limit windows the server reported."""
    parts: list[str] = []
    if api.burst_remaining is not None:
        limit = f"/{api.burst_limit}" if api.burst_limit is not None else ""
        parts.append(f"{api.burst_remaining}{limit} this minute")
    if api.sustained_remaining is not None:
        limit = f"/{api.sustained_limit}" if api.sustained_limit is not None else ""
        parts.append(f"{api.sustained_remaining}{limit} today")
    return ", ".join(parts)


def _has_any(c: _Counts) -> bool:
    return any(
        (
            c.auto_write,
            c.prompt_accepted,
            c.prompt_declined,
            c.skip,
            c.no_match,
            c.explicit_id,
        )
    )


def _format_summary(c: _Counts, per_source: dict[str, _Counts]) -> list[str]:
    total = (
        c.auto_write
        + c.prompt_accepted
        + c.prompt_declined
        + c.skip
        + c.no_match
        + c.explicit_id
    )
    lines = [f"Online tagging summary ({total} comic-sources):"]
    if c.auto_write:
        lines.append(f"  {c.auto_write:>4} auto-written")
    if c.explicit_id:
        lines.append(f"  {c.explicit_id:>4} fetched by --id")
    if c.prompt_accepted or c.prompt_declined:
        lines.append(
            f"  {c.prompt_accepted + c.prompt_declined:>4} prompted "
            f"(chose {c.prompt_accepted}, declined {c.prompt_declined})"
        )
    if c.skip:
        lines.append(f"  {c.skip:>4} skipped (matcher declined)")
    if c.no_match:
        lines.append(
            f"  {c.no_match:>4} no-match (nothing scored above min_confidence)"
        )
    if len(per_source) > 1:
        lines.append("  by source:")
        lines.extend(_format_per_source_lines(per_source))
    return lines


def _format_per_source_lines(per_source: dict[str, _Counts]) -> list[str]:
    """Format the by-source breakdown rows."""
    out: list[str] = []
    for src in sorted(per_source):
        sc = per_source[src]
        parts: list[str] = []
        if sc.auto_write:
            parts.append(f"{sc.auto_write} auto")
        if sc.explicit_id:
            parts.append(f"{sc.explicit_id} id-fetch")
        if sc.prompt_accepted or sc.prompt_declined:
            parts.append(f"{sc.prompt_accepted + sc.prompt_declined} prompted")
        if sc.skip:
            parts.append(f"{sc.skip} skip")
        if sc.no_match:
            parts.append(f"{sc.no_match} no-match")
        out.append(f"    {src}: {', '.join(parts)}")
    return out


# Process-wide singleton.
_STATS = _OutcomeStats()


# Module-level shims so callers don't need to know about the singleton class.
reset = _STATS.reset
record_auto_write = _STATS.record_auto_write
record_prompt_accepted = _STATS.record_prompt_accepted
record_prompt_declined = _STATS.record_prompt_declined
record_skip = _STATS.record_skip
record_no_match = _STATS.record_no_match
record_explicit_id = _STATS.record_explicit_id
record_http_request = _STATS.record_http_request
record_gate_wait = _STATS.record_gate_wait
record_rate_limit_rejection = _STATS.record_rate_limit_rejection
record_unthrottled_response = _STATS.record_unthrottled_response
record_connection_failure = _STATS.record_connection_failure
record_rate_limit_windows = _STATS.record_rate_limit_windows
api_snapshot = _STATS.api_snapshot
has_any_activity = _STATS.has_any_activity
summary_lines = _STATS.summary_lines
