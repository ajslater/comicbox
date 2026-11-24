"""
Where mokkari's `Session` meets comicbox's `RateGate`.

mokkari's own `_check_rate_limit` is a fail-fast that reads the last
response's headers and compares an epoch-valued reset against the LOCAL
clock. That contract works for a sequential caller on a correct clock.
It does not survive a thread pool: the check is not serialized with the
send, so several workers pass it in the same instant, and
`_update_rate_limit_status` is last-write-wins, so a slow response can
put a stale ``remaining`` back on record after a fresher ``0`` was seen.
The result is a burst of 429s -- and on Metron a burst 429 debits the
daily quota exactly like a successful request, because DRF evaluates
each throttle class independently.

So pacing has to happen at the point where a request actually leaves the
process. comicbox used to get there by subclassing `Session` and
overriding the private `_execute_http_request`. That was upstream ask U1
in `tasks/metron-rate-limit-plan.md`, and mokkari 4.8.0 shipped it
(#167): `Session(rate_limiter=...)` dispatches `acquire` /
`on_rate_limited` / `release` from that same single point, and with a
limiter set `_check_rate_limit` is never called at all. The override is
gone; `GateRateLimiter` below is the registration that replaced it.

### Why comicbox keeps `RateGate` and not mokkari's `HeaderPacedRateLimiter`

4.8.0 ships a reference limiter. comicbox does not adopt it. 5.1.0
closed one gap: it now holds each slot 2 s past Metron's 60 s window,
the slack `RateGate` already had (mokkari#198). The rest remain:

| Concern | `RateGate` (comicbox) | `HeaderPacedRateLimiter` (mokkari) |
| --- | --- | --- |
| Before the first response | `UNKNOWN` serializes to one in-flight send, so the first response's headers land before a pool can burst | `limit=None` means no wait at all; N threads send at once |
| A server that never throttles | flips to `OPEN` and stops gating | keeps pacing at whatever it last saw (never, so never paces) |
| Stale out-of-order responses | tighten-only with an in-flight discount | tighten-only for sustained; burst re-read from every response |
| A 429 | rebuilds the server's window and admits ONE worker at `Retry-After`, pacing the rest behind it | blocks EVERY caller until `now + Retry-After`, then spaces evenly |
| Daily quota | warns at 10 %, stops cold searches at 2 %/min 25, aborts with `OnlineLookupAbortedError` at 0 (5.1.1's `Skipped(reason="quota_reserved")` depends on this) | raises `RateLimitError` from the server's epoch reset against the LOCAL clock -- the clock-drift trap the gate was designed around |
| `rate_limit.per_minute` ceiling | honoured, as `config_limit` | none |
| Stats for the end-of-run summary | `stats()` | none |
| Clock | monotonic only; never converts a `-Reset` | mixes monotonic (burst) and wall clock (sustained, and since 5.1.0 an exhausted burst's `-Reset`, capped at one window) |

4.9.0 adds `RedisRateLimiter`, which paces the same way but keeps its
state in Redis so several processes on one account share a window. The
table applies to it too (it reads the Redis server's clock instead of
the local one), and it needs a Redis server, which a CLI tool and
library has no business requiring. comicbox shares one gate across
threads, not processes.

### The one remaining private reach

The `rate_limiter` hook carries no URL, no status code and no raw
headers. comicbox's telemetry -- per-endpoint request counts, and
"responses that arrived without rate-limit headers, by status", both
shipped in 5.1.2 and reported to Metron's maintainer -- needs all three.
So header observation stays where it can see the raw response, on a
`requests` response hook: a public, stable extension point reached
through one private attribute, `Session._http`. Pacing no longer depends
on any private seam. If mokkari renames `_http`,
`install_response_observer` raises `AttributeError` at session build and
the suite fails loudly, which is the same fail-loud posture the old
override had over a far smaller reach. A public accessor is upstream
ask U7.

Since mokkari 5.2.0 the observer also tells apart two sends `release`
cannot: it is passed None both for a send that produced no response and
for a response without `X-RateLimit-*` headers. The hook runs only on a
response, so it marks the send answered, and `GateRateLimiter.release`
counts a connection failure only for a send it never marked.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import mokkari
from loguru import logger

# Imported by name on purpose: these are mokkari's own header constants,
# so an upstream rename breaks the import rather than quietly parsing
# nothing and leaving the gate in its UNKNOWN state forever.
from mokkari.rate_limit import (
    HEADER_BURST_LIMIT,
    HEADER_BURST_REMAINING,
    HEADER_BURST_RESET,
    HEADER_SUSTAINED_LIMIT,
    HEADER_SUSTAINED_REMAINING,
    HEADER_SUSTAINED_RESET,
)

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.warn_once import warn_once

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    import requests
    from mokkari.rate_limit import RateLimitStatus
    from mokkari.session import Session

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


# Hooks a reading-list fetch sets around one mokkari call (see fetch_hooks).
# mokkari fetches every page of a list inside that one blocking call, and it
# is synchronous, so its rate-limiter and response hooks run on the calling
# thread and see these. Unset by default: tagging neither cancels inside a
# call nor counts pages, and behaves exactly as it did without them.


@dataclass(frozen=True, slots=True)
class _FetchHooks:
    """The hooks one fetch set, and the thread they belong to."""

    thread: int
    abort: Callable[[], bool] | None
    on_page: Callable[[requests.Response], None] | None

    def here(self) -> bool:
        """Whether this is the thread that set them."""
        # A thread can inherit a context: a free-threaded build's threads
        # do, as does one run with Context.run. The hooks are not its own.
        return threading.get_ident() == self.thread


_fetch_hooks: ContextVar[_FetchHooks | None] = ContextVar(
    "comicbox_metron_fetch_hooks", default=None
)


@contextmanager
def fetch_hooks(
    *,
    abort: Callable[[], bool] | None = None,
    on_page: Callable[[requests.Response], None] | None = None,
) -> Generator[None]:
    """
    Watch the mokkari calls this thread makes inside the block.

    ``abort`` is asked before each send, and while the send waits at the
    gate: when it returns true, the call raises
    ``OnlineLookupAbortedError``. ``on_page`` sees every raw response,
    after the gate has; it must not raise, and a raise is logged and
    dropped like any other observer failure. Other threads never see
    them, even one that inherits this context.
    """
    token = _fetch_hooks.set(_FetchHooks(threading.get_ident(), abort, on_page))
    try:
        yield
    finally:
        _fetch_hooks.reset(token)


def _here() -> _FetchHooks | None:
    """Get the hooks this thread set, if any."""
    hooks = _fetch_hooks.get()
    return hooks if hooks is not None and hooks.here() else None


def _abort_hook() -> Callable[[], bool] | None:
    """Get the abort hook this thread set, if any."""
    hooks = _here()
    return hooks.abort if hooks is not None else None


def _abort_if_asked() -> None:
    if (abort := _abort_hook()) is not None and abort():
        reason = "Metron fetch cancelled."
        raise OnlineLookupAbortedError(reason)


class _SendState(threading.local):
    """Per-thread record of the send in flight between acquire and release."""

    answered = False


class GateRateLimiter:
    """
    Adapts a `RateGate` to mokkari's `RateLimiter` protocol.

    mokkari dispatches `acquire` immediately before every HTTP send and
    `release` after it returns, from the one frame every public method
    funnels through, on the sending thread. The protocol is not
    `runtime_checkable`; mokkari duck-types it and turns a missing method
    into `RateLimiterError`.

    Only `acquire` can stop a run. Since mokkari 4.9.0 an exception from
    `on_rate_limited` or `release` is logged and ignored, so neither may
    raise to abort; both must do their bookkeeping and return.

    One Session, and so one limiter, serves the whole ``-j N`` pool, so
    whether the send in flight was answered is kept per thread.
    """

    def __init__(self, gate: RateGate) -> None:
        """Pace one Session through ``gate``."""
        self._gate = gate
        self._send = _SendState()

    @property
    def gate(self) -> RateGate:
        """The gate this limiter paces through."""
        return self._gate

    def acquire(self, status: RateLimitStatus) -> None:  # noqa: ARG002
        """
        Block at the gate until a slot is free, recording the wait.

        ``status`` is deliberately unused. It is mokkari's own merged
        view -- `RateLimitStatus.merge_headers` keeps the previous window
        when a response carries none -- so it cannot tell a header-less
        response from the one before it, and folding it in after the
        response observer already did would pad the log a second time.
        Header observation belongs to the observer, which sees the raw
        response.

        Raises `OnlineLookupAbortedError` when the daily quota is spent.
        mokkari wraps only a missing method here, so the abort propagates
        out of the list or detail call, and `with_retry` never replays
        it. mokkari calls `_acquire_rate_limit_slot` BEFORE its
        try/finally, so a raise here is never paired with a `release`.
        """
        _abort_if_asked()
        started = time.monotonic()
        # The gate asks the hook while it waits, so a cancel does not sit
        # out a wait that can last a minute.
        admitted = self._gate.acquire(abort=_abort_hook())
        self._send.answered = False
        outcome_stats.record_gate_wait("metron", time.monotonic() - started)
        try:
            # A cancel that came as the slot freed is honoured before the send.
            _abort_if_asked()
        except OnlineLookupAbortedError:
            # Nothing was sent: give the slot back, uncounted. mokkari never
            # releases a slot whose acquire raised.
            self._gate.withdraw(admitted)
            raise

    def mark_answered(self) -> None:
        """Record that the send in flight on this thread got a response."""
        self._send.answered = True

    def on_rate_limited(self, retry_after: float) -> None:
        """
        Rebuild the server's window around a 429's `Retry-After`.

        mokkari passes 0 when the response carried no `Retry-After`; the
        gate reads None as "assume the whole window is spent", which is
        what keeps the paced retry path from planning a zero delay and
        firing its whole budget back-to-back.
        """
        outcome_stats.record_rate_limit_rejection("metron")
        self._gate.cooldown(retry_after if retry_after > 0 else None)

    def release(self, status: RateLimitStatus | None) -> None:  # noqa: ARG002
        """
        Release the slot `acquire` took.

        A send the response observer never marked answered produced no
        response: mokkari re-raises `requests` ConnectionError and
        ReadTimeout as `ApiError` from the same frame. Counting those
        separately matters because a firewall-level ban (Metron's
        fail2ban jail drops the IP) looks like nothing else from in here
        -- no status, no headers, just timeouts.

        ``status`` is deliberately unused. Since mokkari 5.2.0 it is None
        for a response that carried no `X-RateLimit-*` headers too, so it
        cannot tell a proxy or bot-check page from a send that never
        answered. The observer can, because it only runs on a response.

        The gate's log entry stays either way: a send that never answered
        may well have arrived and been counted by the server.
        """
        if not self._send.answered:
            outcome_stats.record_connection_failure("metron")
        self._gate.release()


def install_response_observer(session: Session, limiter: GateRateLimiter) -> None:
    """
    Feed every raw response's rate-limit headers to the gate and the stats.

    The hook fires inside `Session._http.request(...)`, so it runs
    BEFORE mokkari's `_update_rate_limit_status`, `_report_rate_limited`
    and `release`. That preserves the order the old override had:
    observe, then cool down, then release. Observing before the release
    matters -- the gate's in-flight count still includes this request, so
    its tighten-only math discounts only the OTHER sends the server may
    not have counted yet. It also marks the send answered, so ``limiter``'s
    `release` does not count it as a connection failure.
    """

    def _observe_response(response: requests.Response, **_kwargs: Any) -> None:
        # A `requests` response hook runs inside `_http.request`, outside
        # mokkari's `except (ConnectionError, ReadTimeout)`. An exception
        # escaping here would surface as some other error entirely, so
        # nothing in this hook may raise. Marking the send answered comes
        # first, so even a failed observation is not miscounted as a
        # connection failure.
        try:
            limiter.mark_answered()
            _feed_gate(limiter.gate, response)
            if (hooks := _here()) is not None and hooks.on_page is not None:
                hooks.on_page(response)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"metron: rate-limit observation failed: {exc!r}")

    # The pooled requests.Session is private; see the module docstring.
    session._http.hooks["response"].append(_observe_response)  # noqa: SLF001


def build_paced_session(gate: RateGate, **session_kwargs: Any) -> Session:
    """
    Build a mokkari Session paced by ``gate`` and observed for telemetry.

    `mokkari.api()` is usable again now that no subclass is needed. Its
    keyword set is ``api_token``, ``cache``, ``user_agent``, ``dev_mode``
    and ``rate_limiter``; the token is the only credential mokkari 5.0
    takes.
    """
    limiter = GateRateLimiter(gate)
    session = mokkari.api(rate_limiter=limiter, **session_kwargs)
    install_response_observer(session, limiter)
    return session


def _feed_gate(gate: RateGate, response: requests.Response) -> None:
    """Fold one response's rate-limit headers into the gate and the stats."""
    headers = response.headers
    request = response.request
    outcome_stats.record_http_request("metron", endpoint_from_url(request.url or ""))
    saw_headers = any(name in headers for name in _RATE_LIMIT_HEADERS)
    rejected = response.status_code == _TOO_MANY_REQUESTS
    if not saw_headers:
        _report_unthrottled(response)
    # A header-less 429 has nothing to teach the gate: every window
    # figure is None, so `observe` would only log "pacing disabled" on
    # its way to a `cooldown` that overrides it a moment later, and
    # `record_rate_limit_windows` would be a no-op. Worse, it would flip
    # the gate OPEN a moment before the cooldown sets it PACED.
    if saw_headers or not rejected:
        _observe_headers(gate, headers, saw_headers=saw_headers)


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
