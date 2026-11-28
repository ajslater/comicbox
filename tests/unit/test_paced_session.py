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

import contextlib
import contextvars
import sys
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online import outcome_stats, warn_once
from comicbox.formats.base.online.rate_gate import GateState, RateGate
from comicbox.formats.metron_api import paced_session
from comicbox.formats.metron_api.paced_session import (
    GateRateLimiter,
    build_paced_session,
    endpoint_from_url,
    fetch_hooks,
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

if TYPE_CHECKING:
    from collections.abc import Callable

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

_IF_MODIFIED = datetime(2020, 1, 1, tzinfo=UTC)


class _RecordingGate(RateGate):
    """A real gate that also counts how often it was entered."""

    def __init__(self) -> None:
        super().__init__(default_limit=1000)
        self.acquires = 0
        self.releases = 0
        self.observes = 0
        self.cooldowns: list[float | None] = []

    @override
    def acquire(self, abort: Callable[[], bool] | None = None) -> float:
        self.acquires += 1
        return super().acquire(abort)

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
    return build_paced_session(gate, api_token="t", cache=None)


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
        install_response_observer(not_a_session, GateRateLimiter(gate))


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
    the other thing this looks like, as long as the answer is JSON.
    """
    from loguru import logger as loguru_logger

    json_only = {"Content-Type": "application/json"}
    session, _adapter = _paged(
        gate, [Reply(issue_page([issue_row(1)]), headers=json_only)]
    )

    messages, handler_id = _warnings()
    try:
        session.issues_list(params={"series_id": 7})
    finally:
        loguru_logger.remove(handler_id)

    api = outcome_stats.api_snapshot()["metron"]
    assert api.unthrottled == {200: 1}
    assert api.connection_failures == 0
    assert gate.observes == 1
    assert gate._state is GateState.OPEN
    assert sum("no X-RateLimit-* headers" in m for m in messages) == 1


def _bare_response(status: int, content_type: str | None) -> Any:
    """Build a response with no rate-limit headers, as a proxy or Anubis sends."""
    import requests

    response = requests.Response()
    response.status_code = status
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    response.request = requests.Request(
        "GET", "https://metron.cloud/api/issue/"
    ).prepare()
    return response


@pytest.mark.parametrize(
    ("status", "content_type"),
    [
        (200, "text/html; charset=utf-8"),
        (502, "text/html"),
        (503, None),
        (500, "application/json"),
    ],
    ids=["challenge-page", "proxy-error", "bare-503", "json-5xx"],
)
def test_a_bare_answer_that_is_not_the_api_leaves_the_gate_unknown(
    status: int, content_type: str | None
) -> None:
    """
    B16: one bot-check page as the first response unpaced every worker.

    A header-less answer turns pacing off only when it looks like the API
    answering: a 2xx with a JSON body. Anything else leaves the gate
    UNKNOWN, which keeps serializing until a real answer arrives.
    """
    gate = RateGate(default_limit=20)

    paced_session._feed_gate(gate, _bare_response(status, content_type))

    assert gate._state is GateState.UNKNOWN


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "application/vnd.api+json"],
)
def test_a_bare_json_answer_still_opens_the_gate(content_type: str) -> None:
    """A server that never throttles answers JSON without the headers."""
    gate = RateGate(default_limit=20)

    paced_session._feed_gate(gate, _bare_response(200, content_type))

    assert gate._state is GateState.OPEN


def test_a_bare_answer_is_still_counted_when_it_teaches_nothing() -> None:
    gate = RateGate(default_limit=20)

    paced_session._feed_gate(gate, _bare_response(200, "text/html"))

    api = outcome_stats.api_snapshot()["metron"]
    assert api.unthrottled == {200: 1}
    assert sum(api.requests.values()) == 1


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

    api = outcome_stats.api_snapshot()["metron"]
    assert api.unthrottled == {429: 1}
    assert api.connection_failures == 0
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


@pytest.mark.parametrize(
    "answered_first",
    [True, False],
    ids=["answered-then-failed", "failed-then-answered"],
)
def test_an_answered_send_does_not_leak_to_the_next(
    gate: _RecordingGate, *, answered_first: bool
) -> None:
    """
    Whether a send was answered is decided per send, not per thread.

    Since mokkari 5.2.0 `release` gets None for a header-less answer as
    well as for no answer, so the response observer marks the send
    answered and `acquire` clears the mark. Two sends on one thread, one
    of each kind, in either order, count exactly one failure.
    """
    from mokkari.exceptions import ApiError

    answered = Reply(issue_page([issue_row(1)]), headers={})
    failed = connection_error()
    replies = [answered, failed] if answered_first else [failed, answered]
    session, _adapter = _paged(gate, replies)

    for _ in range(2):
        with contextlib.suppress(ApiError):
            session.issues_list(params={"series_id": 7})

    api = outcome_stats.api_snapshot()["metron"]
    assert api.connection_failures == 1
    assert api.unthrottled == {200: 1}


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


# ------------------------------------------- reading-list hooks (S2)
#
# A reading-list fetch sets an abort check and a page observer around its
# mokkari call. Tagging never sets them, so tagging must behave exactly
# as it did before they existed.


def _hooks() -> Any:
    return paced_session._fetch_hooks.get()


def test_the_hooks_are_unset_by_default() -> None:
    assert _hooks() is None


def test_without_hooks_a_paged_call_is_unchanged(gate: _RecordingGate) -> None:
    """One slot per page and every page sent, as before the hooks."""
    session, adapter = _paged(
        gate,
        [
            Reply(issue_page([issue_row(1)], "https://metron.cloud/api/issue/?page=2")),
            Reply(issue_page([issue_row(2)])),
        ],
    )

    issues = session.issues_list(params={"series_id": 7})

    assert [issue.id for issue in issues] == [1, 2]
    assert len(adapter.urls) == 2
    assert (gate.acquires, gate.releases, gate.observes) == (2, 2, 2)


def test_the_hooks_are_unset_after_the_block_even_on_error() -> None:
    seen: list[Any] = []

    def fail_inside() -> None:
        with fetch_hooks(abort=lambda: True, on_page=lambda _response: None):
            seen.append(_hooks())
            reason = "boom"
            raise RuntimeError(reason)

    with pytest.raises(RuntimeError):
        fail_inside()

    assert seen[0] is not None
    assert _hooks() is None


def test_hooks_do_not_reach_a_thread_that_inherits_them(
    gate: _RecordingGate,
) -> None:
    """
    A thread started inside a fetch, in a copy of its context, is not hooked.

    Free-threaded builds start threads in their creator's context, and
    ``Context.run`` does the same anywhere: a tagging call on such a thread
    must not be cancelled by, or report pages to, a reading-list fetch.
    """
    session, adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])
    pages: list[Any] = []
    results: list[Any] = []

    def tag() -> None:
        assert _hooks() is not None  # It did inherit them.
        results.append(session.issues_list(params={"series_id": 7}))

    with fetch_hooks(abort=lambda: True, on_page=pages.append):
        worker = threading.Thread(target=contextvars.copy_context().run, args=(tag,))
        worker.start()
        worker.join()

    assert [issue.id for issue in results[0]] == [1]
    assert len(adapter.urls) == 1
    assert pages == []


def test_the_abort_check_stops_a_call_before_its_send(gate: _RecordingGate) -> None:
    session, adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])

    with fetch_hooks(abort=lambda: True), pytest.raises(OnlineLookupAbortedError):
        session.issues_list(params={"series_id": 7})

    assert adapter.urls == []
    assert gate.acquires == 0


def test_a_failing_page_observer_cannot_break_a_send(gate: _RecordingGate) -> None:
    session, _adapter = _paged(gate, [Reply(issue_page([issue_row(1)]))])

    def explode(_response: Any) -> None:
        reason = "observer bug"
        raise RuntimeError(reason)

    with fetch_hooks(on_page=explode):
        issues = session.issues_list(params={"series_id": 7})

    assert [issue.id for issue in issues] == [1]
    assert gate.observes == 1


# ------------------------------------------- a forgotten day still spent (F1)

_WORKERS = 4


class _ArrivalGate(RateGate):
    """A real gate that records each send's arrival before it may wait."""

    def __init__(self) -> None:
        super().__init__(default_limit=20)
        self.arrived = threading.Semaphore(0)

    @override
    def acquire(self, abort: Callable[[], bool] | None = None) -> float:
        self.arrived.release()
        return super().acquire(abort)


def test_after_a_forget_a_spent_day_costs_one_request() -> None:
    """
    F1: a reused gate sent one request per worker into a spent day.

    `forget_sustained` left the gate PACED at its learned burst limit, so
    every worker of the next run was admitted before the first answer
    could say the day was still spent: N 429s, enough at -j 30 for
    Metron's ban. A fresh process's gate is UNKNOWN and sends one. The
    fake server holds its answer until every worker has reached the gate,
    so the unfixed gate admits them all deterministically.
    """
    from mokkari.exceptions import RateLimitError

    gate = _ArrivalGate()
    gate.observe(
        burst_limit=30, burst_remaining=30, sustained_limit=5000, sustained_remaining=0
    )
    gate.forget_sustained()
    spent_day = {
        "X-RateLimit-Burst-Limit": "30",
        "X-RateLimit-Burst-Remaining": "29",
        "X-RateLimit-Sustained-Limit": "5000",
        "X-RateLimit-Sustained-Remaining": "0",
        "Retry-After": "3600",
    }

    first = threading.Lock()

    def answer(_request: Any) -> Reply:
        if first.acquire(blocking=False):  # hold only the first answer
            for _ in range(_WORKERS):
                assert gate.arrived.acquire(timeout=10)
        return Reply(status_code=429, headers=spent_day)

    session = _session(gate)
    adapter = install(session, answer)
    start = threading.Barrier(_WORKERS)
    outcomes: list[type[BaseException]] = []
    lock = threading.Lock()

    def worker() -> None:
        start.wait(timeout=10)
        try:
            session.issues_list(params={"series_id": 7})
        except (OnlineLookupAbortedError, RateLimitError) as exc:
            with lock:
                outcomes.append(type(exc))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(_WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not any(thread.is_alive() for thread in threads)
    assert len(adapter.urls) == 1
    # The one sent gets the 429; the rest stop at the gate on the day.
    assert len(outcomes) == _WORKERS
    assert outcomes.count(OnlineLookupAbortedError) == _WORKERS - 1
