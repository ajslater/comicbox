"""
Guard tests for `PacedSession`.

`PacedSession` overrides a PRIVATE mokkari method, `_execute_http_request`.
That is deliberate — it is the one place mokkari calls `requests.request`,
so it is the only place a gate can sit that covers list calls, detail
fetches, every page of a paginated result and conditional GETs alike. The
risk of reaching into a private seam is that an upstream rename makes the
override silently stop overriding anything, leaving comicbox unpaced and
back to earning 429s.

So these drive REAL mokkari methods against a fake transport and assert
one gate acquisition per HTTP send. If mokkari moves the seam, these fail
rather than the behavior quietly disappearing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from typing_extensions import override

from comicbox.formats.base.online import outcome_stats, warn_once
from comicbox.formats.base.online.rate_gate import GateState, RateGate
from comicbox.formats.metron_api.paced_session import PacedSession, endpoint_from_url

_BURST_HEADERS = {
    "X-RateLimit-Burst-Limit": "20",
    "X-RateLimit-Burst-Remaining": "19",
    "X-RateLimit-Sustained-Limit": "5000",
    "X-RateLimit-Sustained-Remaining": "4999",
}


def _issue_row(issue_id: int) -> dict[str, Any]:
    """Build a BaseIssue payload with every field mokkari requires."""
    return {
        "id": issue_id,
        "number": str(issue_id),
        "cover_date": "2020-01-01",
        "modified": "2020-01-01T00:00:00-05:00",
        "issue_name": f"Test #{issue_id}",
        "series": {
            "id": 7,
            "name": "Test Series",
            "volume": 1,
            "year_began": 2020,
        },
    }


class _FakeResponse:
    """Just enough of `requests.Response` for mokkari's handling path."""

    def __init__(
        self, payload: dict[str, Any], status_code: int = 200, headers: Any = None
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = dict(_BURST_HEADERS if headers is None else headers)
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            err = requests.exceptions.HTTPError(f"{self.status_code}")
            # A duck-typed stand-in; requests only reads `.status_code`.
            err.response = self  # ty: ignore[invalid-assignment]  # pyright: ignore[reportAttributeAccessIssue]
            raise err

    def json(self) -> dict[str, Any]:
        return self._payload


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


def _session(gate: RateGate | None) -> PacedSession:
    return PacedSession(gate=gate, username="u", passwd="p", cache=None)


def _install_transport(
    monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResponse]
) -> list[str]:
    """Replace mokkari's `requests.request`; return the URLs it is handed."""
    seen: list[str] = []
    queue = list(responses)

    def fake_request(_method: str, url: str, **_kwargs: Any) -> _FakeResponse:
        seen.append(url)
        return queue.pop(0)

    monkeypatch.setattr("mokkari.session.requests.request", fake_request)
    return seen


# --------------------------------------------------- one acquire per send


def test_list_call_takes_exactly_one_slot(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    page = {"count": 1, "next": None, "previous": None, "results": [_issue_row(1)]}
    urls = _install_transport(monkeypatch, [_FakeResponse(page)])

    issues = _session(gate).issues_list(params={"series_id": 7})

    assert len(issues) == 1
    assert len(urls) == 1
    assert gate.acquires == 1
    assert gate.releases == 1


def test_every_page_of_a_paginated_result_takes_a_slot(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """
    Pagination is the case a wrapper one level up would miss.

    `issues_list` is one call to us and N HTTP requests to Metron, each
    one debiting both throttle windows. Gating `_request_data` would
    catch these but miss detail fetches; gating the wrapper method would
    catch neither.
    """
    page1 = {
        "count": 2,
        "next": "https://metron.cloud/api/issue/?page=2",
        "previous": None,
        "results": [_issue_row(1)],
    }
    page2 = {"count": 2, "next": None, "previous": None, "results": [_issue_row(2)]}
    urls = _install_transport(monkeypatch, [_FakeResponse(page1), _FakeResponse(page2)])

    issues = _session(gate).issues_list(params={"series_id": 7})

    assert len(issues) == 2
    assert len(urls) == 2
    assert gate.acquires == 2
    assert gate.releases == 2


def test_conditional_detail_fetch_takes_a_slot(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """
    `issue(id, if_modified_since=...)` goes through `_fetch_detail`.

    A 304 costs a request against both windows exactly like a 200 does,
    so it has to be paced even though it carries no body.
    """
    urls = _install_transport(monkeypatch, [_FakeResponse({}, status_code=304)])

    result = _session(gate).issue(
        1, if_modified_since=datetime(2020, 1, 1, tzinfo=timezone.utc)
    )

    assert result is None
    assert len(urls) == 1
    assert gate.acquires == 1
    assert gate.releases == 1


def test_a_failed_send_still_releases_its_slot(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """A connection error must not leak an in-flight count and wedge the gate."""
    import requests

    def boom(*_args: Any, **_kwargs: Any) -> None:
        msg = "down"
        raise requests.exceptions.ConnectionError(msg)

    monkeypatch.setattr("mokkari.session.requests.request", boom)

    with pytest.raises(Exception, match="Connection error"):
        _session(gate).issues_list(params={"series_id": 7})

    assert gate.acquires == 1
    assert gate.releases == 1


def test_no_gate_leaves_mokkari_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a gate, `PacedSession` is an ordinary Session."""
    page = {"count": 1, "next": None, "previous": None, "results": [_issue_row(1)]}
    urls = _install_transport(monkeypatch, [_FakeResponse(page)])

    assert len(_session(None).issues_list(params={"series_id": 7})) == 1
    assert len(urls) == 1


# ------------------------------------------------------- header feedback


def test_response_headers_reach_the_gate(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    page = {"count": 1, "next": None, "previous": None, "results": [_issue_row(1)]}
    _install_transport(monkeypatch, [_FakeResponse(page)])

    _session(gate).issues_list(params={"series_id": 7})

    stats = gate.stats()
    assert stats.burst_limit == 20
    assert stats.burst_remaining == 19
    assert stats.sustained_limit == 5000
    assert stats.sustained_remaining == 4999


def test_a_429_cools_the_gate_down_with_the_server_hint(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """
    The gate reacts to the rejection, and mokkari still raises.

    Both halves matter: the gate stops sending, and `with_retry` keeps
    owning the replay.
    """
    from mokkari.exceptions import RateLimitError

    headers = {**_BURST_HEADERS, "X-RateLimit-Burst-Remaining": "0", "Retry-After": "7"}
    _install_transport(
        monkeypatch, [_FakeResponse({}, status_code=429, headers=headers)]
    )

    with pytest.raises(RateLimitError):
        _session(gate).issues_list(params={"series_id": 7})

    assert gate.cooldowns == [7.0]
    assert gate.stats().rejections == 1


def test_mokkari_local_pre_emption_is_disabled(gate: _RecordingGate) -> None:
    """
    The gate replaces mokkari's own check, which is not safe here.

    mokkari compares the epoch-valued reset header against the LOCAL
    clock, so a NAS or container whose clock has drifted raises for a
    window that already cleared — and under threads the check races the
    send it guards.
    """
    session = _session(gate)
    session._update_rate_limit_status(
        {
            "X-RateLimit-Burst-Limit": "20",
            "X-RateLimit-Burst-Remaining": "0",
            "X-RateLimit-Burst-Reset": "99999999999",
        }
    )
    session._check_rate_limit()  # would raise on a plain Session


def test_without_a_gate_mokkari_keeps_its_own_check(gate: _RecordingGate) -> None:
    """Suppression is tied to the gate, not to the subclass."""
    from mokkari.exceptions import RateLimitError

    session = _session(None)
    session._update_rate_limit_status(
        {
            "X-RateLimit-Burst-Limit": "20",
            "X-RateLimit-Burst-Remaining": "0",
            "X-RateLimit-Burst-Reset": "99999999999",
        }
    )
    with pytest.raises(RateLimitError):
        session._check_rate_limit()


# ------------------------------------------ responses that missed the API


def test_a_response_without_rate_limit_headers_is_bucketed_by_status(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
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

    page = {"count": 1, "next": None, "previous": None, "results": [_issue_row(1)]}
    _install_transport(monkeypatch, [_FakeResponse(page, headers={})])

    messages, handler_id = _warnings()
    try:
        _session(gate).issues_list(params={"series_id": 7})
    finally:
        loguru_logger.remove(handler_id)

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {200: 1}
    assert gate.observes == 1
    assert gate._state is GateState.OPEN
    assert sum("no X-RateLimit-* headers" in m for m in messages) == 1


def test_a_header_less_429_cools_down_without_teaching_the_gate(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """
    Nothing to observe, everything to cool down.

    Every window figure on a bare 429 is None, so `observe` would do
    nothing but log "pacing disabled" on its way to a `cooldown` that
    contradicts it a moment later. The cooldown is unchanged — a full
    window rebuild — because the paced retry path plans a zero delay and
    would otherwise spend its whole budget back-to-back.
    """
    from mokkari.exceptions import RateLimitError

    _install_transport(monkeypatch, [_FakeResponse({}, status_code=429, headers={})])

    with pytest.raises(RateLimitError):
        _session(gate).issues_list(params={"series_id": 7})

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {429: 1}
    assert gate.observes == 0
    assert gate.cooldowns == [None]
    assert gate.stats().rejections == 1


def test_a_headered_304_is_not_counted_as_unthrottled(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """A conditional GET is a real API response and carries the headers."""
    _install_transport(monkeypatch, [_FakeResponse({}, status_code=304)])

    _session(gate).issue(1, if_modified_since=datetime(2020, 1, 1, tzinfo=timezone.utc))

    assert outcome_stats.api_snapshot()["metron"].unthrottled == {}


def test_a_transport_failure_is_counted_separately(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """
    A send that never produced a response gets its own counter.

    mokkari re-raises `requests` ConnectionError and ReadTimeout as
    `ApiError` from the one frame the gate wraps; an HTTP status error is
    raised further up and never reaches it. This is the only shape a
    firewall-level ban has from in here — Metron's fail2ban jail drops
    the IP, so the client just stops getting answers.
    """
    import requests

    def boom(*_args: Any, **_kwargs: Any) -> None:
        msg = "down"
        raise requests.exceptions.ConnectionError(msg)

    monkeypatch.setattr("mokkari.session.requests.request", boom)

    with pytest.raises(Exception, match="Connection error"):
        _session(gate).issues_list(params={"series_id": 7})

    api = outcome_stats.api_snapshot()["metron"]
    assert api.connection_failures == 1
    assert api.requests == {"issue_list": 1}
    assert api.unthrottled == {}


# ------------------------------------------------------------ accounting


def test_requests_are_counted_per_endpoint(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    page = {"count": 1, "next": None, "previous": None, "results": [_issue_row(1)]}
    _install_transport(
        monkeypatch, [_FakeResponse(page), _FakeResponse({}, status_code=304)]
    )

    session = _session(gate)
    session.issues_list(params={"series_id": 7})
    session.issue(1, if_modified_since=datetime(2020, 1, 1, tzinfo=timezone.utc))

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
