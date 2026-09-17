"""
A mokkari `Session` that paces every request through a `RateGate`.

mokkari is documented to raise rather than wait, and its own
`_check_rate_limit` is a fail-fast that reads the last response's
headers. That contract works for a sequential caller. It does not
survive a thread pool: the check is not serialized with the send, so
several workers pass it in the same instant, and
`_update_rate_limit_status` is last-write-wins, so a slow response can
put a stale ``remaining`` back on record after a fresher ``0`` was seen.
The result is a burst of 429s — and on Metron a burst 429 debits the
daily quota exactly like a successful request, because DRF evaluates
each throttle class independently.

So pacing has to happen at the point where a request actually leaves the
process, under the same lock that counts it. That point is
`Session._execute_http_request`: the one place mokkari calls
`requests.request`, and the one place it reads ``X-RateLimit-*`` back.
Its three callers — `_request_data`, `_fetch_detail` and `_send_void` —
funnel every path through it: after the response-cache check in `_get`,
once per page in `_retrieve_all_results`, and on conditional
``if_modified_since`` GETs. Overriding `_request_data` instead would
miss detail fetches and void sends.

This is a deliberate reach into a private method. `tests/unit/
test_paced_session.py` drives a fake transport through those paths and
asserts one gate acquisition per HTTP send, so a mokkari rename fails
loudly here instead of silently unpacing the client. The upstream ask
that retires it is `tasks/metron-rate-limit-plan.md` U1 — an opt-in
`Session(rate_limiter=...)` hook — after which this collapses to a
registration.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

# Imported by name on purpose: these are mokkari's own header constants,
# so an upstream rename breaks the import rather than quietly parsing
# nothing and leaving the gate in its UNKNOWN state forever.
from mokkari.session import (
    HEADER_BURST_LIMIT,
    HEADER_BURST_REMAINING,
    HEADER_BURST_RESET,
    HEADER_SUSTAINED_LIMIT,
    HEADER_SUSTAINED_REMAINING,
    HEADER_SUSTAINED_RESET,
    Session,
)
from typing_extensions import override

from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.warn_once import warn_once

if TYPE_CHECKING:
    import requests

    from comicbox.formats.base.online.rate_gate import RateGate

_TOO_MANY_REQUESTS = 429

_RATE_LIMIT_HEADERS = (
    HEADER_BURST_LIMIT,
    HEADER_BURST_REMAINING,
    HEADER_BURST_RESET,
    HEADER_SUSTAINED_LIMIT,
    HEADER_SUSTAINED_REMAINING,
    HEADER_SUSTAINED_RESET,
)


def _header_int(headers: Any, name: str) -> int | None:
    """Read one integer header, tolerating absence and junk."""
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def endpoint_from_url(url: str) -> str:
    """
    Name the API endpoint a URL addresses, for per-endpoint accounting.

    ``/api/issue/`` is a list call and ``/api/issue/1234/`` is a detail
    fetch; they cost the same against the quota but mean very different
    things in a cost report, so they get distinct names. The names match
    mokkari's own method names (``issue_list``, ``issue``) so a summary
    line reads the way the code does.
    """
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if not parts:
        return "other"
    endpoint = parts[0]
    is_detail = len(parts) > 1 and parts[1].isdigit()
    return endpoint if is_detail else f"{endpoint}_list"


class PacedSession(Session):
    """A mokkari Session whose every HTTP send passes through a gate."""

    def __init__(self, *, gate: RateGate | None = None, **kwargs: Any) -> None:
        """Build a Session, optionally paced by ``gate``."""
        super().__init__(**kwargs)
        self._gate = gate

    @override
    def _check_rate_limit(self) -> None:
        """
        Disabled: the gate owns pacing now.

        mokkari's check compares the epoch-valued ``X-RateLimit-*-Reset``
        against the LOCAL clock, so on a NAS or in a container whose
        clock has drifted it raises `RateLimitError` for a window that
        has actually cleared — and under threads it races the send it is
        meant to guard. The gate replaces it with a monotonic sliding log
        that is serialized with the send and never reads a wall clock.

        Left as an override rather than deleted so the method still
        exists on this class: if mokkari renames it, the `@override`
        check fails instead of this silently ceasing to suppress
        anything.
        """
        if self._gate is None:
            super()._check_rate_limit()

    @override
    def _execute_http_request(
        self,
        method: str,
        url: str,
        params: dict[str, str | int],
        header: dict[str, str],
        data_dict: str | dict[str, Any] | None,
        files: dict[str, tuple[str, bytes]] | None,
    ) -> requests.Response:
        """Wait for a slot, send, then feed the response's headers back."""
        gate = self._gate
        if gate is None:
            return super()._execute_http_request(
                method, url, params, header, data_dict, files
            )
        started = time.monotonic()
        gate.acquire()
        blocked = time.monotonic() - started
        try:
            response = super()._execute_http_request(
                method, url, params, header, data_dict, files
            )
        except Exception:
            # A send that never produced a response still consumed a slot
            # as far as the server is concerned (it may well have arrived
            # and been counted), so the log entry `acquire` made stays.
            #
            # Everything that lands here is a transport failure: mokkari
            # catches `requests` ConnectionError and ReadTimeout and
            # re-raises them as `ApiError`, while an HTTP status error is
            # raised later, out of `_handle_http_response`, and never
            # reaches this frame. Counting them separately matters
            # because a firewall-level ban (Metron's fail2ban jail drops
            # the IP) looks like nothing else from in here: no status, no
            # headers, just timeouts.
            outcome_stats.record_http_request("metron", endpoint_from_url(url), blocked)
            outcome_stats.record_connection_failure("metron")
            raise
        else:
            # Observe BEFORE releasing, so the gate's in-flight count
            # still includes this request and its tighten-only math
            # discounts only the OTHER sends the server may not have
            # counted yet.
            self._feed_gate(gate, url, response, blocked)
            return response
        finally:
            gate.release()

    def _feed_gate(
        self, gate: RateGate, url: str, response: requests.Response, blocked: float
    ) -> None:
        """Fold one response's rate-limit headers into the gate and the stats."""
        headers = response.headers
        endpoint = endpoint_from_url(url)
        outcome_stats.record_http_request("metron", endpoint, blocked)
        saw_headers = any(name in headers for name in _RATE_LIMIT_HEADERS)
        rejected = response.status_code == _TOO_MANY_REQUESTS
        if not saw_headers:
            _report_unthrottled(response)
        # A header-less 429 has nothing to teach the gate: every window
        # figure is None, so `observe` would only log "pacing disabled"
        # on its way to a `cooldown` that overrides it a moment later,
        # and `record_rate_limit_windows` would be a no-op. Skip straight
        # to the rejection path. The cooldown itself is unchanged — a
        # full-window rebuild — because without it the paced retry path
        # plans a zero delay and fires its whole budget back-to-back.
        if saw_headers or not rejected:
            _observe_headers(gate, headers, saw_headers=saw_headers)
        if not rejected:
            return
        # Metron attaches X-RateLimit-* to 429s too, so the headers above
        # are already folded in. `Retry-After` is the relative hint that
        # says when ONE slot frees; the gate rebuilds the server's window
        # around it. mokkari turns this response into a RateLimitError a
        # moment later, which `with_retry` replays.
        outcome_stats.record_rate_limit_rejection("metron")
        gate.cooldown(_retry_after_hint(headers))


def _observe_headers(gate: RateGate, headers: Any, *, saw_headers: bool) -> None:
    """Feed one response's rate-limit windows to the gate and the stats."""
    burst_limit = _header_int(headers, HEADER_BURST_LIMIT)
    burst_remaining = _header_int(headers, HEADER_BURST_REMAINING)
    sustained_limit = _header_int(headers, HEADER_SUSTAINED_LIMIT)
    sustained_remaining = _header_int(headers, HEADER_SUSTAINED_REMAINING)
    gate.observe(
        burst_limit=burst_limit,
        burst_remaining=burst_remaining,
        sustained_limit=sustained_limit,
        sustained_remaining=sustained_remaining,
        sustained_reset=_header_int(headers, HEADER_SUSTAINED_RESET),
        saw_headers=saw_headers,
    )
    outcome_stats.record_rate_limit_windows(
        "metron",
        burst_limit=burst_limit,
        burst_remaining=burst_remaining,
        sustained_limit=sustained_limit,
        sustained_remaining=sustained_remaining,
    )


def _report_unthrottled(response: requests.Response) -> None:
    """
    Count and announce a response that carried no rate-limit headers.

    Metron's middleware copies `X-RateLimit-*` onto every response whose
    request reached DRF's throttles, and those run in `initial()` ahead
    of all view code, so a real `/api/` answer of ANY status carries
    them. A bare response therefore did not come from the API: it is a
    proxy error page, or a bot-check challenge — Anubis serves both its
    challenge and its deny page as HTTP 200 HTML by default.

    Status, Content-Type and Content-Length are enough to tell those
    apart and are safe to log. The body is not logged: mokkari's
    `ApiError` already embeds `response.text` on the paths that fail, and
    the `Server` header is not logged because nginx overwrites it.
    """
    status = response.status_code
    outcome_stats.record_unthrottled_response("metron", status)
    headers = response.headers
    warn_once(
        "metron:no-rate-limit-headers",
        "metron: a response arrived with no X-RateLimit-* headers "
        f"(status {status}, "
        f"content-type {headers.get('Content-Type', 'unset')}, "
        f"content-length {headers.get('Content-Length', 'unset')}). "
        "Metron's API sets those on every response, so this one came "
        "from something in front of it. The end-of-run summary counts "
        "them all.",
    )


def _retry_after_hint(headers: Any) -> float | None:
    """Read `Retry-After` as relative seconds, tolerating absence and junk."""
    raw = headers.get("Retry-After")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
