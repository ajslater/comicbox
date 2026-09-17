"""
The acceptance test for issue #207: a `-j N` batch earns no 429s.

Everything else about the rate gate is asserted in isolation. This drives
a real thread pool through a real `PacedSession` against a transport that
enforces Metron's throttle the way Metron does — a sliding log of send
timestamps, per DRF's `SimpleRateThrottle` — and counts what the server
refused.

It matters that this runs offline and in CI. The stress harnesses in
`tests/stress/` answer the same question against live Metron, but they
need credentials, take minutes, and cost the very quota the change exists
to protect; nothing would have caught a regression here between runs of
them.

The windows are shortened (1s instead of 60s) so the test finishes in
about a second. That is the only thing faked: the gate's arithmetic and
the server's are both the real ones, scaled.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from comicbox.formats.base.online import rate_gate
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.metron_api.paced_session import PacedSession

# Scaled-down mirror of Metron's `DEFAULT_THROTTLE_RATES["burst"]`.
_SERVER_WINDOW_S = 1.0
_SERVER_LIMIT = 20
_REQUESTS = 50
_WORKERS = 8


class _ThrottlingTransport:
    """
    Stands in for Metron's DRF throttle.

    A sliding LOG, not a counter reset on a boundary: a slot frees exactly
    one window after the request that took it, which is what makes
    `Retry-After` mean "one slot frees" rather than "the window refills".
    """

    def __init__(self, limit: int = _SERVER_LIMIT) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._history: list[float] = []
        self.rejections = 0
        self.accepted = 0

    def __call__(self, _method: str, url: str, **_kwargs: Any) -> _Response:
        with self._lock:
            now = time.monotonic()
            self._history = [t for t in self._history if t > now - _SERVER_WINDOW_S]
            if len(self._history) >= self._limit:
                self.rejections += 1
                # DRF's `wait()`: when the OLDEST entry ages out.
                retry_after = self._history[0] + _SERVER_WINDOW_S - now
                return _Response(429, self._headers(0), max(0.0, retry_after))
            self._history.append(now)
            self.accepted += 1
            remaining = self._limit - len(self._history)
            return _Response(200, self._headers(remaining))

    def _headers(self, remaining: int) -> dict[str, str]:
        """Metron attaches these to every response, 429s included."""
        return {
            "X-RateLimit-Burst-Limit": str(self._limit),
            "X-RateLimit-Burst-Remaining": str(remaining),
            "X-RateLimit-Sustained-Limit": "5000",
            "X-RateLimit-Sustained-Remaining": "4999",
        }


class _Response:
    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        retry_after: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = dict(headers)
        if retry_after is not None:
            self.headers["Retry-After"] = f"{retry_after:.3f}"
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            err = requests.exceptions.HTTPError(str(self.status_code))
            # Duck-typed stand-in; requests only reads `.status_code`.
            err.response = self  # ty: ignore[invalid-assignment]  # pyright: ignore[reportAttributeAccessIssue]
            raise err

    def json(self) -> dict[str, Any]:
        return {"count": 0, "next": None, "previous": None, "results": []}


@pytest.fixture(autouse=True)
def _short_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scale the gate's window to the transport's, so this runs in ~1s."""
    monkeypatch.setattr(rate_gate, "_WINDOW_S", _SERVER_WINDOW_S)
    monkeypatch.setattr(rate_gate, "_SLACK_S", 0.05)


def _drive(session: PacedSession) -> None:
    """Run `_REQUESTS` list calls through `_WORKERS` threads."""

    def one(_i: int) -> None:
        session.issues_list(params={"series_id": 7})

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for future in [pool.submit(one, i) for i in range(_REQUESTS)]:
            future.result()


def test_a_paced_pool_earns_no_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The whole point of #207.

    Every rejection Metron issues also debits the daily quota, because
    DRF evaluates each throttle class independently. So a 429 is not a
    retryable inconvenience — it is budget spent on nothing, and the only
    way to stop paying it is not to send the request.
    """
    transport = _ThrottlingTransport()
    monkeypatch.setattr("mokkari.session.requests.request", transport)
    gate = RateGate(default_limit=_SERVER_LIMIT)
    session = PacedSession(gate=gate, username="u", passwd="p", cache=None)

    _drive(session)

    assert transport.rejections == 0
    assert transport.accepted == _REQUESTS
    assert gate.stats().sends == _REQUESTS
    assert gate.stats().rejections == 0


def test_the_same_load_unpaced_does_earn_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Proves the test above is testing something.

    Without a gate this is what comicbox did: `--jobs` bounded workers,
    not requests, so a pool walked straight past the window. mokkari's
    own `_check_rate_limit` cannot prevent it — it reads the last
    response's headers and is not serialized with the send.
    """
    transport = _ThrottlingTransport()
    monkeypatch.setattr("mokkari.session.requests.request", transport)
    session = PacedSession(gate=None, username="u", passwd="p", cache=None)

    with pytest.raises(Exception, match="Rate Limit"):
        _drive(session)

    assert transport.rejections > 0


def test_pacing_holds_the_pool_to_the_server_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Zero rejections must come from pacing, not from running slowly.

    50 requests at 20 per window cannot finish in under two window
    lifetimes, and should not take many more than that — a gate that
    bought compliance by serializing everything would be correct and
    useless.
    """
    transport = _ThrottlingTransport()
    monkeypatch.setattr("mokkari.session.requests.request", transport)
    gate = RateGate(default_limit=_SERVER_LIMIT)
    session = PacedSession(gate=gate, username="u", passwd="p", cache=None)

    started = time.monotonic()
    _drive(session)
    elapsed = time.monotonic() - started

    assert transport.rejections == 0
    # floor((50 - 1) / 20) windows of waiting, at minimum.
    assert elapsed >= 2 * _SERVER_WINDOW_S
    assert elapsed < 6 * _SERVER_WINDOW_S


def test_a_rejection_from_elsewhere_does_not_cascade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Another client on the same token spent the window; we recover from it.

    The failure mode this guards is the one in the issue's logs: every
    worker sleeps the same `Retry-After`, wakes together and sends
    together, so one rejection becomes a burst of them. Here the gate
    rebuilds the server's window and releases one worker per freed slot,
    while `with_retry` replays the call that was refused — the full
    production stack, source through gate, because the division of labour
    between those two layers is the thing under test.
    """
    from comicbox.config.online.settings import (
        OnlineSettings,
        OnlineSourceCredentials,
    )
    from comicbox.formats.metron_api.online_source import MetronOnlineSource

    transport = _ThrottlingTransport()
    # Somebody else already filled the window.
    with transport._lock:
        transport._history = [time.monotonic()] * _SERVER_LIMIT
    monkeypatch.setattr("mokkari.session.requests.request", transport)
    gate = RateGate(default_limit=_SERVER_LIMIT)
    session = PacedSession(gate=gate, username="u", passwd="p", cache=None)
    src = MetronOnlineSource(
        OnlineSourceCredentials(user="u", password="p"), OnlineSettings()
    )
    monkeypatch.setattr(src, "_get_session", lambda: session)

    def one() -> None:
        src._issues_list_with_retry(session, {"series_id": 7})

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for future in [pool.submit(one) for _ in range(_WORKERS)]:
            future.result()  # no worker gives up

    # One worker discovers the spent window; the gate absorbs it and the
    # rest queue behind that rather than each finding out the hard way.
    assert transport.rejections == 1
    assert transport.accepted == _WORKERS
