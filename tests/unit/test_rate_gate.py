"""
Unit tests for the online request rate gate.

Driven by a fake monotonic clock so the sliding log's timing is asserted
exactly instead of slept through. `_wait_seconds` is exercised through
`_pending_wait` rather than by calling `acquire` on a full gate, which
would really block.
"""

from __future__ import annotations

import pytest

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.rate_gate import (
    _SLACK_S,
    _WINDOW_S,
    GateState,
    RateGate,
)

_LIFETIME = _WINDOW_S + _SLACK_S


class _Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def _gate(clock: _Clock, **kwargs) -> RateGate:
    kwargs.setdefault("default_limit", 4)
    return RateGate(clock=clock, **kwargs)


def _pending_wait(gate: RateGate) -> float:
    """Return what `acquire` would wait for now, without blocking on it."""
    with gate._cond:
        now = gate._clock()
        gate._expire(now)
        return gate._wait_seconds(now)


def _paced(gate: RateGate, limit: int = 4) -> None:
    """Move the gate out of UNKNOWN without spending a slot."""
    gate.observe(burst_limit=limit, burst_remaining=limit)


def _send(gate: RateGate) -> None:
    """One complete request: through the gate and back out."""
    gate.acquire()
    gate.release()


# ----------------------------------------------------------- sliding log


def test_log_admits_exactly_the_limit_per_window(clock: _Clock) -> None:
    """The window holds `limit` sends; the next one has to wait."""
    gate = _gate(clock)
    _paced(gate)
    for _ in range(4):
        _send(gate)
    assert _pending_wait(gate) == pytest.approx(_LIFETIME)


def test_a_slot_frees_one_lifetime_after_it_was_stamped(clock: _Clock) -> None:
    """
    Slots age out individually, so the gate drips rather than batching.

    The slack matters: DRF stamps its history when the request is
    received, after TLS and auth, so the server's copy of a slot outlives
    ours. Freeing at exactly 60s would spend the next send on a 429.
    """
    gate = _gate(clock)
    _paced(gate)
    _send(gate)
    clock.advance(10.0)
    for _ in range(3):
        _send(gate)
    assert _pending_wait(gate) == pytest.approx(_LIFETIME - 10.0)

    # The first slot ages out; exactly one send gets through.
    clock.advance(_LIFETIME - 10.0)
    assert _pending_wait(gate) == 0.0
    _send(gate)
    assert _pending_wait(gate) > 0.0


def test_unknown_state_serializes_until_the_first_response(clock: _Clock) -> None:
    """One request in flight until the server has said what the limit is."""
    gate = _gate(clock)
    assert _pending_wait(gate) == 0.0
    gate.acquire()  # in flight, no response yet
    assert _pending_wait(gate) > 0.0
    gate.release()
    assert _pending_wait(gate) == 0.0


# --------------------------------------------------------------- limits


def test_server_header_replaces_the_default_limit(clock: _Clock) -> None:
    gate = _gate(clock, default_limit=4)
    gate.observe(burst_limit=2, burst_remaining=2)
    assert gate._limit() == 2


def test_config_limit_tightens_but_never_widens(clock: _Clock) -> None:
    """The knob is a share of the window, not a licence to exceed it."""
    tight = _gate(clock, default_limit=20, config_limit=5)
    tight.observe(burst_limit=20, burst_remaining=20)
    assert tight._limit() == 5

    greedy = _gate(clock, default_limit=20, config_limit=500)
    greedy.observe(burst_limit=20, burst_remaining=20)
    assert greedy._limit() == 20


# ------------------------------------------------------ header feedback


def test_remaining_tightens_a_too_optimistic_local_estimate(clock: _Clock) -> None:
    """Another client on the token spent slots we never logged."""
    gate = _gate(clock, default_limit=10)
    gate.observe(burst_limit=10, burst_remaining=10)
    _send(gate)
    assert _pending_wait(gate) == 0.0
    # The server says only one slot is left, not nine.
    gate.observe(burst_limit=10, burst_remaining=1)
    assert _pending_wait(gate) == 0.0
    _send(gate)
    assert _pending_wait(gate) > 0.0


def test_a_stale_response_can_never_widen_the_estimate(clock: _Clock) -> None:
    """
    Responses land out of order under a pool; the tighter one has to win.

    This is the exact failure mode mokkari's last-write-wins
    `_update_rate_limit_status` has: a slow response carrying
    `remaining=5` arriving after a fresh `remaining=0` puts the optimistic
    number back on record.
    """
    gate = _gate(clock, default_limit=10)
    gate.observe(burst_limit=10, burst_remaining=0)
    blocked = _pending_wait(gate)
    assert blocked > 0.0
    gate.observe(burst_limit=10, burst_remaining=5)
    assert _pending_wait(gate) == pytest.approx(blocked)


def test_other_in_flight_sends_come_off_the_reported_remaining(
    clock: _Clock,
) -> None:
    """The server cannot have counted requests that have not landed yet."""
    gate = _gate(clock, default_limit=10)
    gate.observe(burst_limit=10, burst_remaining=10)
    gate.acquire()  # the one being observed
    gate.acquire()  # a sibling the server has not seen
    gate.acquire()  # and another
    # remaining=3 with 2 other sends outstanding means 1 usable slot.
    gate.observe(burst_limit=10, burst_remaining=3)
    gate.release()
    gate.release()
    gate.release()
    assert _pending_wait(gate) == 0.0
    _send(gate)
    assert _pending_wait(gate) > 0.0


def test_no_rate_limit_headers_opens_the_gate(clock: _Clock) -> None:
    """A self-hosted Metron with throttling off is not paced at all."""
    gate = _gate(clock, default_limit=1)
    gate.observe(burst_limit=None, burst_remaining=None, saw_headers=False)
    assert gate._state is GateState.OPEN
    for _ in range(50):
        _send(gate)
    assert _pending_wait(gate) == 0.0


def test_one_header_less_response_does_not_unpace_a_paced_gate(
    clock: _Clock,
) -> None:
    """A cached or proxied response is a blip, not a policy change."""
    gate = _gate(clock, default_limit=2)
    _paced(gate, limit=2)
    gate.observe(burst_limit=None, burst_remaining=None, saw_headers=False)
    assert gate._state is GateState.PACED
    for _ in range(2):
        _send(gate)
    assert _pending_wait(gate) > 0.0


# ------------------------------------------------------------- cooldown


def test_cooldown_admits_one_at_the_deadline_then_paces_the_rest(
    clock: _Clock,
) -> None:
    """
    `Retry-After` frees ONE slot, and the gate must not release a queue.

    Metron's `Retry-After` (and `X-RateLimit-*-Reset`) is when its oldest
    history entry ages out. A client that sleeps that long and then lets
    every worker go gets one request through and N-1 fresh 429s, each of
    which also debits the daily quota. So the gate rebuilds the whole
    window: one send at the deadline, the rest at the steady-state pace
    behind it.
    """
    gate = _gate(clock, default_limit=4)
    _paced(gate)
    gate.cooldown(10.0)

    assert _pending_wait(gate) == pytest.approx(10.0)

    clock.advance(10.0)
    assert _pending_wait(gate) == 0.0
    _send(gate)

    # The second worker does not get to follow it through.
    spacing = _LIFETIME / 4
    assert _pending_wait(gate) == pytest.approx(spacing)
    clock.advance(spacing)
    assert _pending_wait(gate) == 0.0


def test_cooldown_without_a_hint_waits_out_a_whole_window(clock: _Clock) -> None:
    """A 429 from in front of Django carries no Retry-After."""
    gate = _gate(clock, default_limit=4)
    _paced(gate)
    gate.cooldown(None)
    assert _pending_wait(gate) == pytest.approx(_WINDOW_S)


def test_cooldown_repaces_a_gate_that_had_been_opened(clock: _Clock) -> None:
    """
    A rejection is proof of throttling even when no headers came with it.

    Without this the retry loop — which plans a zero delay for a paced
    source and comes straight back — would spin on the rejection.
    """
    gate = _gate(clock, default_limit=4)
    gate.observe(burst_limit=None, burst_remaining=None, saw_headers=False)
    assert gate._state is GateState.OPEN
    gate.cooldown(5.0)
    assert gate._state is GateState.PACED
    assert _pending_wait(gate) == pytest.approx(5.0)


def test_cooldown_counts_as_a_rejection(clock: _Clock) -> None:
    gate = _gate(clock)
    gate.cooldown(1.0)
    gate.cooldown(1.0)
    assert gate.stats().rejections == 2


# ---------------------------------------------------- sustained watermarks


def test_sustained_warns_once_under_ten_percent(clock: _Clock) -> None:
    from loguru import logger as loguru_logger

    gate = _gate(clock)
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        gate.observe(
            burst_limit=4,
            burst_remaining=4,
            sustained_limit=5000,
            sustained_remaining=450,
        )
        gate.observe(
            burst_limit=4,
            burst_remaining=4,
            sustained_limit=5000,
            sustained_remaining=440,
        )
    finally:
        loguru_logger.remove(handler_id)
    assert sum("daily API requests remaining" in m for m in messages) == 1


def test_sustained_above_the_warn_line_is_quiet(clock: _Clock) -> None:
    from loguru import logger as loguru_logger

    gate = _gate(clock)
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        gate.observe(
            burst_limit=4,
            burst_remaining=4,
            sustained_limit=5000,
            sustained_remaining=2000,
        )
    finally:
        loguru_logger.remove(handler_id)
    assert not messages


def test_cold_searches_stop_at_the_reserve(clock: _Clock) -> None:
    """The last of the day goes to finishing comics, not starting them."""
    gate = _gate(clock)
    assert gate.allow_cold_search()  # nothing reported yet
    gate.observe(
        burst_limit=4, burst_remaining=4, sustained_limit=5000, sustained_remaining=200
    )
    assert gate.allow_cold_search()
    gate.observe(
        burst_limit=4, burst_remaining=4, sustained_limit=5000, sustained_remaining=40
    )
    assert not gate.allow_cold_search()


def test_exhausted_daily_quota_aborts_instead_of_sending(clock: _Clock) -> None:
    """
    At zero there is nothing to gain by trying: a 429 costs a day-slot too.

    Metron evaluates each throttle class independently, so a rejected
    request debits the sustained quota exactly like a successful one.
    """
    gate = _gate(clock)
    gate.observe(
        burst_limit=4, burst_remaining=4, sustained_limit=5000, sustained_remaining=0
    )
    with pytest.raises(OnlineLookupAbortedError, match="quota exhausted"):
        gate.acquire()


# ---------------------------------------------------------------- stats


def test_stats_report_sends_and_the_reported_windows(clock: _Clock) -> None:
    gate = _gate(clock)
    _paced(gate)
    _send(gate)
    _send(gate)
    gate.observe(
        burst_limit=4, burst_remaining=2, sustained_limit=5000, sustained_remaining=4998
    )
    stats = gate.stats()
    assert stats.sends == 2
    assert stats.rejections == 0
    assert stats.burst_limit == 4
    assert stats.burst_remaining == 2
    assert stats.sustained_remaining == 4998
