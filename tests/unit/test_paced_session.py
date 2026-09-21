"""
Guard tests for the mokkari `rate_limiter` adoption.

Pacing reaches mokkari through a public hook now (`GateRateLimiter`),
but telemetry still rides one private attribute, `Session._http`, via a
`requests` response hook. These tests drive REAL mokkari methods against
a fake transport adapter mounted on that pooled session and assert one
gate acquisition per HTTP send, so if mokkari moves either seam they
fail rather than the behavior quietly disappearing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest
from typing_extensions import override

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online import outcome_stats, warn_once
from comicbox.formats.base.online.rate_gate import GateState, RateGate
from comicbox.formats.metron_api.paced_session import (
    GateRateLimiter,
    build_paced_session,
    endpoint_from_url,
    install_response_observer,
)
from tests.util.metron_transport import (
    BURST_HEADERS,
    Reply,
    connection_error,
    install,
    issue_page,
    issue_row,
)

_IF_MODIFIED = datetime(2020, 1, 1, tzinfo=timezone.utc)


class _RecordingGate(RateGate):
    """A real gate that also counts how often it was entered."""

    def __init__(self) -> None:
        super().__init__(default_limit=1000)
        self.acquires = 0
        self.releases = 0
        self.observes = 0
        self.cooldowns: list[float | None] = []

    @override
    def acquire(self) -> None:
        self.acquires += 1
        super().acquire()

    @override
    def release(self) -> None:
        self.releases += 1
        super().release()

    @override
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
        self.observes += 1
        super().observe(
            burst_limit=burst_limit,
            burst_remaining=burst_remaining,
            sustained_limit=sustained_limit,
            sustained_remaining=sustained_remaining,
            sustained_reset=sustained_reset,
            saw_headers=saw_headers,
        )

    @override
    def cooldown(self, retry_after: float | None) -> None:
        self.cooldowns.append(retry_after)
        super().cooldown(retry_after)


class _NoWaitGate(_RecordingGate):
    """
    Records a cooldown without serving out the wait.

    For tests about mokkari's retry bound rather than the gate's timing:
    a real cooldown with no `Retry-After` rebuilds the whole 60-second
    window, and three of those in a row is three minutes of real sleep to
    prove a counter.
    """

    @override
    def cooldown(self, retry_after: float | None) -> None:
        self.cooldowns.append(retry_after)


@pytest.fixture(autouse=True)
def _reset_stats() -> None:
    outcome_stats.reset()


@pytest.fixture(autouse=True)
def _reset_warn_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """`warn_once` dedups for the life of the process; tests get a clean set."""
    monkeypatch.setattr(warn_once, "_seen", set())


def _warnings() -> tuple[list[str], int]:
    """Collect WARNING-level loguru records; caller removes the handler."""
    from loguru import logger as loguru_logger

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    return messages, handler_id


@pytest.fixture
def gate() -> _RecordingGate:
    return _RecordingGate()


def _session(gate: RateGate) -> Any:
    return build_paced_session(gate, username="u", passwd="p", cache=None)


def _paged(gate: RateGate, replies: list[Reply]) -> tuple[Any, Any]:
    """Build a paced session with a canned transport; return both."""
    session = _session(gate)
    return session, install(session, replies)


# --------------------------------------------------- one acquire per send


def test_the_gate_is_registered_as_the_rate_limiter(gate: _RecordingGate) -> None:
    """
    Mokkari owns the pacing switch now; comicbox only registers.

    With a `rate_limiter` set, mokkari never calls its own
    `_check_rate_limit` -- the local pre-emption comicbox used to
    override away is gone from the code path entirely.
    """
    session = _session(gate)

    assert isinstance(session.rate_limiter, GateRateLimiter)


def test_list_call_takes_exactly_one_slot(gate: _RecordingGate) -> None:
    _session_, adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])

    issues = _session_.issues_list(params={"series_id": 7})

    assert len(issues) == 1
    assert len(adapter.urls) == 1
    assert gate.acquires == 1
    assert gate.releases == 1


def test_every_page_of_a_paginated_result_takes_a_slot(gate: _RecordingGate) -> None:
    """
    Pagination is the case a wrapper one level up would miss.

    `issues_list` is one call to us and N HTTP requests to Metron, each
    one debiting both throttle windows.
    """
    session, adapter = _paged(
        gate,
        [
            Reply(issue_page([issue_row(1)], "https://metron.cloud/api/issue/?page=2")),
            Reply(issue_page([issue_row(2)])),
        ],
    )

    issues = session.issues_list(params={"series_id": 7})

    assert len(issues) == 2
    assert len(adapter.urls) == 2
    assert gate.acquires == 2
    assert gate.releases == 2


def test_conditional_detail_fetch_takes_a_slot(gate: _RecordingGate) -> None:
    """
    `issue(id, if_modified_since=...)` goes through `_fetch_detail`.

    A 304 costs a request against both windows exactly like a 200 does,
    so it has to be paced even though it carries no body.
    """
    session, adapter = _paged(gate, [Reply(status_code=304)])

    result = session.issue(1, if_modified_since=_IF_MODIFIED)

    assert result is None
    assert len(adapter.urls) == 1
    assert gate.acquires == 1
    assert gate.releases == 1


def test_a_failed_send_still_releases_its_slot(gate: _RecordingGate) -> None:
    """A connection error must not leak an in-flight count and wedge the gate."""
    session, _adapter = _paged(gate, [connection_error()])

    with pytest.raises(Exception, match="Connection error"):
        session.issues_list(params={"series_id": 7})

    assert gate.acquires == 1
    assert gate.releases == 1


def test_the_observer_needs_the_pooled_session(gate: _RecordingGate) -> None:
    """
    A mokkari rename of `_http` fails loudly at session build.

    That is the whole point of reaching for a private attribute in the
    open rather than defensively: the suite breaks instead of the
    telemetry silently going quiet.
    """
    not_a_session = cast("Any", object())
    with pytest.raises(AttributeError):
        install_response_observer(not_a_session, gate)


# ------------------------------------------------------- header feedback


def test_response_headers_reach_the_gate(gate: _RecordingGate) -> None:
    session, _adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])

    session.issues_list(params={"series_id": 7})

    stats = gate.stats()
    assert stats.burst_limit == 20
    assert stats.burst_remaining == 19
    assert stats.sustained_limit == 5000
    assert stats.sustained_remaining == 4999


def test_a_429_cools_the_gate_down_with_the_server_hint(gate: _RecordingGate) -> None:
    """
    The gate reacts to the rejection, and mokkari still raises.

    Both halves matter: the gate stops sending, and `with_retry` keeps
    owning the replay.
    """
    from mokkari.exceptions import RateLimitError

    headers = {**BURST_HEADERS, "X-RateLimit-Burst-Remaining": "0", "Retry-After": "7"}
    session, _adapter = _paged(gate, [Reply(status_code=429, headers=headers)])

    with pytest.raises(RateLimitError):
        session.issues_list(params={"series_id": 7})

    assert gate.cooldowns == [7.0]
    assert gate.stats().rejections == 1


# ------------------------------------------ responses that missed the API


def test_a_response_without_rate_limit_headers_is_bucketed_by_status(
    gate: _RecordingGate,
) -> None:
    """
    A bare 200 did not come from Metron's API, and the count says so.

    Every response DRF's throttles touched carries `X-RateLimit-*`, and
    they run ahead of all view code, so an answer without them came from
    nginx or from Anubis — whose challenge and deny pages are both HTTP
    200 HTML. The gate's own handling of a header-less response is
    unchanged: it still opens, because a server that never throttles is
    the other thing this looks like.
    """
    from loguru import logger as loguru_logger

    session, _adapter = _paged(gate, [Reply(issue_page([issue_row(1)]), headers={})])

    messages, handler_id = _warnings()
    try:
        session.issues_list(params={"series_id": 7})
    finally:
        loguru_logger.remove(handler_id)

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {200: 1}
    assert gate.observes == 1
    assert gate._state is GateState.OPEN
    assert sum("no X-RateLimit-* headers" in m for m in messages) == 1


def test_a_header_less_429_cools_down_without_teaching_the_gate(
    gate: _RecordingGate,
) -> None:
    """
    Nothing to observe, everything to cool down.

    Every window figure on a bare 429 is None, so `observe` would do
    nothing but log "pacing disabled" on its way to a `cooldown` that
    contradicts it a moment later. mokkari passes 0 for a missing
    `Retry-After`; the gate reads that as None and rebuilds the whole
    window, because the paced retry path plans a zero delay and would
    otherwise spend its whole budget back-to-back.
    """
    from mokkari.exceptions import RateLimitError

    session, _adapter = _paged(gate, [Reply(status_code=429, headers={})])

    with pytest.raises(RateLimitError):
        session.issues_list(params={"series_id": 7})

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {429: 1}
    assert gate.observes == 0
    assert gate.cooldowns == [None]
    assert gate.stats().rejections == 1


def test_a_headered_304_is_not_counted_as_unthrottled(gate: _RecordingGate) -> None:
    """A conditional GET is a real API response and carries the headers."""
    session, _adapter = _paged(gate, [Reply(status_code=304)])

    session.issue(1, if_modified_since=_IF_MODIFIED)

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {}


def test_a_transport_failure_is_counted_separately(gate: _RecordingGate) -> None:
    """
    A send that never produced a response gets its own counter.

    It is NOT counted under its endpoint any more: `requests` counts
    responses received, which is what the server's own logs show.
    mokkari signals it by passing `status=None` to `release`.

    This is the only shape a firewall-level ban has from in here —
    Metron's fail2ban jail drops the IP, so the client just stops
    getting answers.
    """
    session, _adapter = _paged(gate, [connection_error()])

    with pytest.raises(Exception, match="Connection error"):
        session.issues_list(params={"series_id": 7})

    api = outcome_stats.api_snapshot()["metron"]
    assert api.connection_failures == 1
    assert api.requests == {}
    assert api.unthrottled == {}


# --------------------------------------------- mokkari 4.8.0 pagination


def test_a_paginated_429_retries_through_the_gate_without_sleeping(
    gate: _RecordingGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    With a limiter set, mokkari hands the wait to the gate.

    Before 4.8.0 a 429 mid-pagination slept inside mokkari, on top of
    whatever the gate was already doing. Now the page is simply retried:
    `acquire` blocks on the window the cooldown just rebuilt.
    """
    slept: list[float] = []
    monkeypatch.setattr("mokkari.session.time.sleep", slept.append)
    page2 = "https://metron.cloud/api/issue/?page=2"
    headers = {**BURST_HEADERS, "Retry-After": "1"}
    session, _adapter = _paged(
        gate,
        [
            Reply(issue_page([issue_row(1)], page2)),
            Reply(status_code=429, headers=headers),
            Reply(issue_page([issue_row(2)])),
        ],
    )

    issues = session.issues_list(params={"series_id": 7})

    assert len(issues) == 2
    assert gate.cooldowns == [1.0]
    assert not slept


def test_a_paginated_429_storm_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Untimed 429s stop after a bounded number of retries, not forever.

    mokkari 4.8.0 caps a page's retries at 3 without a `Retry-After`
    (`MAX_UNTIMED_RATE_LIMIT_RETRIES`); before, this looped indefinitely.
    """
    from mokkari.exceptions import RateLimitError

    monkeypatch.setattr("mokkari.session.time.sleep", lambda _s: None)
    page2 = "https://metron.cloud/api/issue/?page=2"
    replies = [Reply(issue_page([issue_row(1)], page2))]
    replies += [Reply(status_code=429, headers=BURST_HEADERS) for _ in range(8)]
    no_wait = _NoWaitGate()
    session, _adapter = _paged(no_wait, replies)

    with pytest.raises(RateLimitError):
        session.issues_list(params={"series_id": 7})

    # Three untimed retries, then the fourth 429 propagates.
    assert no_wait.cooldowns == [None] * 4


def test_a_spent_quota_aborts_from_inside_a_list_call(gate: _RecordingGate) -> None:
    """
    The 5.1.1 abort semantics now hold mid-pagination too.

    `RateGate.acquire` raises `OnlineLookupAbortedError`, not a
    `RateLimitError`, so it propagates straight out of `issues_list`:
    mokkari only wraps `AttributeError` at that seam, and its pagination
    retry only catches `RateLimitError`. Nothing is sent.
    """
    gate.observe(
        burst_limit=20,
        burst_remaining=19,
        sustained_limit=5000,
        sustained_remaining=0,
    )
    session, adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])

    with pytest.raises(OnlineLookupAbortedError):
        session.issues_list(params={"series_id": 7})

    assert not adapter.urls


# ------------------------------------------------------------ accounting


def test_requests_are_counted_per_endpoint(gate: _RecordingGate) -> None:
    session, _adapter = _paged(
        gate, [Reply(issue_page([issue_row(1)])), Reply(status_code=304)]
    )

    session.issues_list(params={"series_id": 7})
    session.issue(1, if_modified_since=_IF_MODIFIED)

    api = outcome_stats.api_snapshot()["metron"]
    assert api.requests == {"issue_list": 1, "issue": 1}
    assert api.sustained_remaining == 4999


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://metron.cloud/api/issue/", "issue_list"),
        ("https://metron.cloud/api/issue/1234/", "issue"),
        ("https://metron.cloud/api/series/99/", "series"),
        ("https://metron.cloud/api/issue/?page=2", "issue_list"),
        ("https://metron.cloud/", "other"),
    ],
)
def test_endpoint_names(url: str, expected: str) -> None:
    assert endpoint_from_url(url) == expected
