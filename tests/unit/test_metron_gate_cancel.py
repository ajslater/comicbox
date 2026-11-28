"""
A Metron request waiting at the rate gate ends when the run is aborted.

The gate waits up to a minute for a slot. Ctrl-C under ``-j N``, or an
abort answered at another worker's prompt, must not sit that out: the
lookup asks the run's abort signals while it waits.
"""

from __future__ import annotations

import sys
import threading
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.box import Comicbox
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online import retry
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.base.online.session_state import OnlineSessionState
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.metron_api.paced_session import build_paced_session
from tests.util.metron_transport import Reply, install, issue_page

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_JOIN_S = 10


class _ParkedGate(RateGate):
    """
    A gate whose one slot is spent under a clock that never moves.

    Any send waits forever unless its abort check fires. `parked` is set
    once a send has started waiting.
    """

    def __init__(self) -> None:
        self.parked = threading.Event()
        self._armed = False
        super().__init__(default_limit=1, clock=lambda: 1000.0)
        self.observe(burst_limit=1, burst_remaining=1)
        super().acquire()
        self.release()
        self._armed = True

    @override
    def acquire(self, abort: Callable[[], bool] | None = None) -> float:
        if self._armed:
            self.parked.set()
        return super().acquire(abort=abort)

    def free(self) -> None:
        """Let a waiter that never checks for an abort out, for cleanup."""
        with self._cond:
            self._slots.clear()
            self._cond.notify_all()


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> Iterator[_ParkedGate]:
    gate = _ParkedGate()
    session = build_paced_session(gate, api_token="t", cache=None)
    install(session, lambda _request: Reply(issue_page([])))
    monkeypatch.setattr(MetronOnlineSource, "_get_session", lambda _self: session)
    retry.clear_cancel()
    yield gate
    gate.free()
    retry.clear_cancel()


def _box() -> Comicbox:
    metadata = {
        "comicbox": {
            "series": {"name": "Lila Lane"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
        }
    }
    return Comicbox(
        config=Namespace(
            comicbox=Namespace(
                online_sources=["metron"],
                general=Namespace(metadata=metadata),
                auth=["metron:key=k"],
            )
        )
    )


def _look_up_parked(
    gate: _ParkedGate, stop: Callable[[OnlineSessionState], Any]
) -> list:
    """Start a lookup, wait until it is parked at the gate, then ``stop``."""
    box = _box()
    state = OnlineSessionState.from_lookup(box._config.online.lookup)
    box.set_online_session_state(state)
    outcome: list = []

    def work() -> None:
        try:
            outcome.append(box.run_online_lookup())
        except OnlineLookupAbortedError as exc:
            outcome.append(exc)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    assert gate.parked.wait(_JOIN_S)
    stop(state)
    worker.join(_JOIN_S)
    finished = not worker.is_alive()
    gate.free()  # an unfixed waiter is still parked; let it go
    worker.join(_JOIN_S)
    assert finished, "the lookup sat out the paced wait"
    return outcome


def test_a_run_abort_ends_a_paced_wait(gate: _ParkedGate) -> None:
    """G1: an abort at another worker's prompt left this one waiting."""
    outcome = _look_up_parked(gate, OnlineSessionState.abort)

    assert len(outcome) == 1
    assert isinstance(outcome[0], OnlineLookupAbortedError)


def test_a_cancel_ends_a_paced_wait(gate: _ParkedGate) -> None:
    """G1: Ctrl-C under ``-j N`` (the retry cancel) left a paced wait running."""
    outcome = _look_up_parked(gate, lambda _state: retry.request_cancel())

    assert len(outcome) == 1
    assert isinstance(outcome[0], OnlineLookupAbortedError)


class _CountingParkedGate(_ParkedGate):
    """A parked gate that counts the sends waiting at it."""

    def __init__(self) -> None:
        self.waiting = threading.Semaphore(0)
        super().__init__()

    @override
    def acquire(self, abort: Callable[[], bool] | None = None) -> float:
        if self._armed:
            self.waiting.release()
        return super().acquire(abort=abort)


def test_a_cancelled_session_ends_its_paced_wait_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    D-5: OnlineSession.cancel() left its lookup waiting out a paced slot.

    Two sessions share one Metron token, so one gate. Cancelling one ends
    that session's wait and sends nothing; the other keeps waiting for
    its slot, because the cancel goes through the session's own state,
    never the process-wide retry cancel.
    """
    from comicbox.online_session import OnlineCredentials, OnlineSession
    from tests.util.comics import make_comic

    gate = _CountingParkedGate()
    session = build_paced_session(gate, api_token="t", cache=None)
    adapter = install(session, lambda _request: Reply(issue_page([])))
    monkeypatch.setattr(MetronOnlineSource, "_get_session", lambda _self: session)
    retry.clear_cancel()

    def comic(name: str):
        return make_comic(
            tmp_path / f"{name} #001 (2020).cbz",
            series=name,
            number="1",
            cover_date="2020-01-01",
        )

    sessions = {
        name: OnlineSession(
            sources={"metron"}, credentials=OnlineCredentials(metron_key="t")
        )
        for name in ("Lila Lane", "Wardens")
    }
    results: dict[str, Any] = {}

    def tag(name: str) -> None:
        results[name] = sessions[name].tag(comic(name))

    threads = {
        name: threading.Thread(target=tag, args=(name,), daemon=True)
        for name in sessions
    }
    try:
        for thread in threads.values():
            thread.start()
        assert gate.waiting.acquire(timeout=_JOIN_S)
        assert gate.waiting.acquire(timeout=_JOIN_S)  # both parked at the gate

        sessions["Lila Lane"].cancel()
        threads["Lila Lane"].join(_JOIN_S)

        assert not threads["Lila Lane"].is_alive()
        assert results["Lila Lane"].cancelled
        assert threads["Wardens"].is_alive()  # still waiting its slot
        assert not retry.is_cancelled()
        assert adapter.urls == []
    finally:
        gate.free()
        for thread in threads.values():
            thread.join(_JOIN_S)
        retry.clear_cancel()
