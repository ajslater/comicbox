"""
Process-wide sliding-log request gate for a rate-limited online source.

Mirrors the shape of the thing it has to satisfy. Metron's DRF backend
paces with ``SimpleRateThrottle``: a per-token LOG of send timestamps,
one slot freeing 60 s after it was stamped. A client that models the same
log and refuses to exceed it never earns a 429 in the first place — which
is the point, because on Metron every burst 429 *also* debits the
5,000/day sustained quota (DRF evaluates each throttle class
independently), so a rejected request costs exactly as much daily budget
as a successful one.

What this is NOT: a retry/backoff mechanism. `retry.py` still owns
replaying a failed call. This owns *not sending* the call early.

Three states, because the right pace is not knowable until the server
says so:

- ``UNKNOWN`` — nothing has come back yet. One request in flight at a
  time, so the first response's headers land before a burst can.
- ``PACED`` — ``X-RateLimit-*`` headers were seen. The sliding log runs
  at the server-reported limit.
- ``OPEN`` — a response arrived carrying no rate-limit headers at all
  (``dev_mode``, a self-hosted Metron with throttling off). Nothing to
  pace against, so the gate stops gating.

Clock discipline: every deadline in here is `time.monotonic()` plus a
RELATIVE offset the server gave us (``Retry-After``). The epoch-valued
``X-RateLimit-*-Reset`` headers are deliberately never turned into a
local deadline — they are the server's clock, and comicbox runs on NAS
boxes and in containers whose clocks drift. The reset headers are used
only for display.

One gate per credential set, owned by the source that builds the client
(see `MetronOnlineSource._get_or_build_shared_session`).
"""

from __future__ import annotations

import datetime
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Final

from loguru import logger

from comicbox.exceptions import OnlineLookupAbortedError

if TYPE_CHECKING:
    from collections.abc import Callable

# The throttle window we are modelling, in seconds.
_WINDOW_S: Final[float] = 60.0

# Added to every slot's lifetime. DRF stamps its history entry when the
# request is *received* — after TLS, routing and auth — while we stamp
# when we hand it to `requests`. The server's copy of a slot therefore
# expires slightly later than ours, and without slack our log would free
# a slot a beat before the server does and spend it on a 429.
_SLACK_S: Final[float] = 2.0

# Ceiling on a single wait inside the gate, so a bad header or a wild
# `Retry-After` can never park a worker indefinitely. A worker that hits
# this re-evaluates rather than gives up.
_MAX_WAIT_S: Final[float] = 300.0

# Sustained-quota watermarks, as a fraction of the reported daily limit.
# WARN is a heads-up only. COLD_FLOOR is where the gate stops admitting
# *discretionary* work (cold searches) so the rest of the day's budget
# goes to finishing files that already matched — a detail fetch completes
# a comic, a search only starts one.
_SUSTAINED_WARN_FRACTION: Final[float] = 0.10
_SUSTAINED_COLD_FLOOR_FRACTION: Final[float] = 0.02

# Absolute floor for the cold-search cutoff, for the case where a small
# reported limit would make the fraction round down to nothing. Roughly
# "enough left to finish the files already in flight".
_SUSTAINED_COLD_FLOOR_MIN: Final[int] = 25


class GateState(Enum):
    """What the gate knows about the server's pace."""

    UNKNOWN = auto()  # no response yet; serialize
    PACED = auto()  # rate-limit headers seen; run the log
    OPEN = auto()  # server does not throttle; stop gating


@dataclass(frozen=True, slots=True)
class GateStats:
    """A snapshot of what the gate has done, for the end-of-run summary."""

    sends: int
    """Requests admitted through the gate (one per real HTTP send)."""
    rejections: int
    """Server rate-limit rejections observed (429s, and local pre-empts)."""
    blocked_seconds: float
    """Total wall-clock seconds workers spent waiting at the gate."""
    burst_remaining: int | None
    burst_limit: int | None
    sustained_remaining: int | None
    sustained_limit: int | None


class RateGate:
    """
    Admission control for one credential set's requests to one API.

    `acquire` blocks until sending is within the server's pace and
    records the send; `release` retires the in-flight count; `observe`
    feeds response headers back in; `cooldown` reacts to an actual
    rejection. Every method is safe to call from any thread.
    """

    def __init__(
        self,
        *,
        default_limit: int,
        config_limit: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Build a gate.

        ``default_limit`` is the documented per-minute cap, used until the
        server reports its own. ``config_limit`` is the user's
        ``rate_limit.per_minute`` override, which only ever TIGHTENS the
        server's number — that is what lets an embedder running several
        processes against one token split the budget between them.
        ``clock`` is injectable so tests can drive a fake monotonic clock.
        """
        self._clock = clock
        self._cond = threading.Condition()
        self._default_limit = max(1, default_limit)
        self._config_limit = config_limit if config_limit and config_limit > 0 else None
        self._state = GateState.UNKNOWN
        # Send timestamps, plus synthetic entries padded in by `observe`
        # and `cooldown` to model slots the server counted and we did
        # not. Only ever counted, never read back as history.
        self._slots: deque[float] = deque()
        self._server_limit: int | None = None
        self._in_flight = 0
        self._sends = 0
        self._rejections = 0
        self._blocked_seconds = 0.0
        self._burst_remaining: int | None = None
        self._sustained_limit: int | None = None
        self._sustained_remaining: int | None = None
        self._sustained_reset: float | None = None  # epoch, display only
        self._sustained_warned = False
        self._cold_search_warned = False

    # -- limits ---------------------------------------------------------------

    def _limit(self) -> int:
        """Effective slots per window: the server's number, user-tightened."""
        limit = self._default_limit
        if self._server_limit is not None:
            limit = self._server_limit
        if self._config_limit is not None:
            limit = min(limit, self._config_limit)
        return max(1, limit)

    def _expire(self, now: float) -> None:
        """Drop slots the server has certainly freed. Caller holds the lock."""
        horizon = now - (_WINDOW_S + _SLACK_S)
        while self._slots and self._slots[0] <= horizon:
            self._slots.popleft()

    def _wait_seconds(self, now: float) -> float:
        """
        How long before a slot is free, or 0 when one already is.

        Caller holds the lock and has already expired the log.
        """
        if self._state is GateState.OPEN:
            return 0.0
        if self._state is GateState.UNKNOWN and self._in_flight:
            # Serialize until the first response teaches us the real
            # limit. No deadline to compute: what this waits on is
            # `release`, which notifies. The log below still applies, at
            # the documented default, so a fast serial burst is paced
            # too.
            return _MAX_WAIT_S
        if len(self._slots) < self._limit():
            return 0.0
        return max(0.0, self._slots[0] + _WINDOW_S + _SLACK_S - now)

    # -- admission ------------------------------------------------------------

    def acquire(self) -> None:
        """
        Block until a send is within pace, then record it.

        Raises `OnlineLookupAbortedError` when the daily quota is spent —
        every further request would be refused, and a 429 costs the same
        daily budget as a success, so there is nothing to gain by trying.
        """
        started = self._clock()
        with self._cond:
            self._check_sustained_exhausted()
            while True:
                now = self._clock()
                self._expire(now)
                wait = self._wait_seconds(now)
                if wait <= 0:
                    self._slots.append(now)
                    self._in_flight += 1
                    self._sends += 1
                    break
                self._cond.wait(min(wait, _MAX_WAIT_S))
            blocked = self._clock() - started
            if blocked > 0:
                self._blocked_seconds += blocked
        if blocked >= 1.0:
            logger.debug(f"online rate gate: paced a request by {blocked:.1f}s")

    def release(self) -> None:
        """Retire one in-flight request and wake a waiter."""
        with self._cond:
            self._in_flight = max(0, self._in_flight - 1)
            self._cond.notify_all()

    # -- feedback -------------------------------------------------------------

    def observe(
        self,
        *,
        burst_limit: int | None,
        burst_remaining: int | None,
        sustained_limit: int | None = None,
        sustained_remaining: int | None = None,
        sustained_reset: float | None = None,
        saw_headers: bool = True,
    ) -> None:
        """
        Fold one response's rate-limit headers into the gate's estimate.

        Tighten-only by construction. Responses come back out of order
        under a thread pool, so a stale ``remaining=5`` must never undo a
        fresher ``remaining=0``: this only ever ADDS slots to the log,
        never removes them, and only ever lowers the remaining figures.
        """
        with self._cond:
            if not saw_headers:
                # Only ever from UNKNOWN. A server that has been sending
                # rate-limit headers and then omits one set is a blip (a
                # cached response, an error page from a proxy), not an
                # announcement that it stopped throttling — mokkari's own
                # header parser preserves prior state for the same
                # reason. Flipping to OPEN on that would unpace a client
                # mid-run.
                if self._state is GateState.UNKNOWN:
                    logger.debug(
                        "online rate gate: server sent no rate-limit headers; "
                        "pacing disabled"
                    )
                    self._state = GateState.OPEN
                    self._cond.notify_all()
                return
            self._state = GateState.PACED
            if burst_limit is not None and burst_limit > 0:
                self._server_limit = burst_limit
            if burst_remaining is not None:
                self._tighten_to_remaining(burst_remaining)
                self._burst_remaining = burst_remaining
            self._update_sustained(
                sustained_limit, sustained_remaining, sustained_reset
            )
            self._cond.notify_all()

    def _tighten_to_remaining(self, server_remaining: int) -> None:
        """
        Pad the log when the server has fewer slots left than we think.

        ``server_remaining`` was computed while the server handled ONE of
        our requests; our other in-flight sends may not be in its count
        yet, so they come off the top. Padding at ``now`` is deliberately
        pessimistic — a synthetic slot lives a full window — but it is
        only reached when our model has already drifted low.
        """
        now = self._clock()
        self._expire(now)
        others_in_flight = max(0, self._in_flight - 1)
        allowed = max(0, server_remaining - others_in_flight)
        local_free = max(0, self._limit() - len(self._slots))
        deficit = local_free - allowed
        for _ in range(deficit):
            self._slots.append(now)

    def _update_sustained(
        self,
        limit: int | None,
        remaining: int | None,
        reset: float | None,
    ) -> None:
        """Record the daily window and warn once when it runs low."""
        if limit is not None and limit > 0:
            self._sustained_limit = limit
        if reset is not None:
            self._sustained_reset = reset
        if remaining is None:
            return
        # Monotonically non-increasing within a run, so an out-of-order
        # response cannot walk the figure back up.
        if self._sustained_remaining is None or remaining < self._sustained_remaining:
            self._sustained_remaining = remaining
        self._warn_sustained_low()

    def _warn_sustained_low(self) -> None:
        """Emit the one-time 10%-remaining heads-up. Caller holds the lock."""
        limit = self._sustained_limit
        remaining = self._sustained_remaining
        if limit is None or remaining is None or self._sustained_warned:
            return
        if remaining > limit * _SUSTAINED_WARN_FRACTION:
            return
        self._sustained_warned = True
        logger.warning(
            f"online: {remaining} of {limit} daily API requests remaining"
            f"{_reset_suffix(self._sustained_reset)}"
        )

    def cooldown(self, retry_after: float | None) -> None:
        """
        React to a rejection by rebuilding the server's window locally.

        ``retry_after`` is the server saying when ONE slot frees — not
        when the window refills (DRF's ``wait()`` returns the time until
        its oldest history entry ages out, and Metron's
        ``X-RateLimit-*-Reset`` is the same moment). A client that sleeps
        that long and then releases its whole queue gets one request
        through and N-1 fresh 429s.

        So instead of parking everyone on one deadline, reconstruct the
        window the server must be holding: a full log whose oldest slot
        frees in ``retry_after`` seconds and whose remaining slots are
        spread across the window after it. The log then admits exactly
        one worker at the deadline and paces the rest behind it, with no
        thundering herd and no dependence on the server's clock.
        """
        with self._cond:
            self._rejections += 1
            # A rejection is proof something is throttling us, even when
            # it arrived without headers (a proxy in front of Django).
            # Leaving the gate OPEN here would let the retry loop — which
            # for a paced source plans a zero delay and comes straight
            # back — spin on the rejection instead of waiting it out.
            self._state = GateState.PACED
            now = self._clock()
            self._expire(now)
            limit = self._limit()
            # Without a usable hint, assume the whole window is spent:
            # every slot ages out one window from now.
            delay = retry_after if retry_after and retry_after > 0 else _WINDOW_S
            delay = min(delay, _MAX_WAIT_S)
            # The oldest slot must have been stamped `_WINDOW_S` before it
            # frees; the rest follow at the steady-state pace.
            oldest = now + delay - (_WINDOW_S + _SLACK_S)
            spacing = (_WINDOW_S + _SLACK_S) / limit
            self._slots = deque(oldest + i * spacing for i in range(limit))
            self._cond.notify_all()
        logger.debug(
            f"online rate gate: rejection; rebuilt a full {limit}-slot window, "
            f"next send in {delay:.1f}s"
        )

    # -- sustained-quota policy ----------------------------------------------

    def _check_sustained_exhausted(self) -> None:
        """Abort the run when the daily quota is gone. Caller holds the lock."""
        if self._sustained_remaining is None or self._sustained_remaining > 0:
            return
        msg = (
            "online: daily API request quota exhausted "
            f"(0 of {self._sustained_limit} remaining)"
            f"{_reset_suffix(self._sustained_reset)}; "
            "stopping. Cached responses make a re-run cheap."
        )
        raise OnlineLookupAbortedError(msg)

    def allow_cold_search(self) -> bool:
        """
        Whether there is enough daily quota left to START a new search.

        False once the remaining daily budget is down to the reserve, so
        what is left goes to detail fetches for comics that already
        matched. Finishing a match is worth more than starting one.
        """
        with self._cond:
            remaining = self._sustained_remaining
            limit = self._sustained_limit
            if remaining is None:
                return True
            floor = _SUSTAINED_COLD_FLOOR_MIN
            if limit is not None:
                floor = max(floor, int(limit * _SUSTAINED_COLD_FLOOR_FRACTION))
            if remaining > floor:
                return True
            warned = self._cold_search_warned
            self._cold_search_warned = True
        if not warned:
            logger.warning(
                f"online: {remaining} daily API requests left; not starting new "
                "searches so the remaining budget finishes comics that already "
                f"matched{_reset_suffix(self._sustained_reset)}"
            )
        return False

    # -- reporting ------------------------------------------------------------

    def stats(self) -> GateStats:
        """Snapshot the counters for the end-of-run summary."""
        with self._cond:
            return GateStats(
                sends=self._sends,
                rejections=self._rejections,
                blocked_seconds=self._blocked_seconds,
                burst_remaining=self._burst_remaining,
                burst_limit=self._server_limit,
                sustained_remaining=self._sustained_remaining,
                sustained_limit=self._sustained_limit,
            )


def _reset_suffix(reset: float | None) -> str:
    """Render a reset epoch for humans, or nothing when unknown."""
    if reset is None:
        return ""
    when = datetime.datetime.fromtimestamp(reset, tz=datetime.timezone.utc)
    return f" (one slot frees at {when.isoformat(timespec='seconds')})"
