"""
A forked child must not inherit an online source's shared clients.

A shared client holds pooled sockets and sqlite connections, which
parent and child must not both write into (codex's librarian process and
`comicbox/process.py`'s pool are the forks). Each test builds a client
through the source's own shared-client path, forks for real, and has the
child report through a pipe whether it was handed the parent's client.
The child arms an alarm, so a lock inherited in its held state kills it
instead of hanging the suite.
"""

from __future__ import annotations

import os
import signal
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from comicbox.config.online.settings import (
    OnlineCacheSettings,
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.formats.comicvine_api import online_source as comicvine
from comicbox.formats.metron_api import online_source as metron
from comicbox.formats.versedb_api import online_source as versedb

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is POSIX only")

_CHILD_TIMEOUT_S = 10


class _Client:
    """A client double: records a close, reads as open."""

    closed = False

    def __init__(self, *_args: Any) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _settings(tmp_path: Path) -> OnlineSettings:
    return OnlineSettings(cache=OnlineCacheSettings(dir=tmp_path))


def _metron(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    source = metron.MetronOnlineSource(
        OnlineSourceCredentials(key="fork-token"), _settings(tmp_path)
    )
    monkeypatch.setattr(source, "_build_session", _Client)
    return source._get_or_build_shared_session


def _comicvine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    source = comicvine.ComicVineOnlineSource(
        OnlineSourceCredentials(key="fork-key"), _settings(tmp_path)
    )
    monkeypatch.setattr(source, "_build_session", _Client)
    return source._get_or_build_shared_session


def _versedb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    source = versedb.VerseDBOnlineSource(
        OnlineSourceCredentials(key="fork-token"), _settings(tmp_path)
    )
    monkeypatch.setattr(source, "_build_client", _Client)
    return source._get_or_build_shared_client


_SOURCES = {"metron": _metron, "comicvine": _comicvine, "versedb": _versedb}


@pytest.fixture(autouse=True)
def _fresh_registries() -> Iterator[None]:
    """Start and end every test with no shared clients in this process."""
    for module in (metron, comicvine, versedb):
        module.reset_shared_sessions()
    yield
    for module in (metron, comicvine, versedb):
        module.reset_shared_sessions()


def _in_child(probe: Callable[[], str]) -> str:
    """Run ``probe`` in a forked child and return what it reported."""
    read_fd, write_fd = os.pipe()
    with warnings.catch_warnings():
        # 3.12+ warns that forking a multi-threaded process may deadlock,
        # which is the very thing under test.
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid == 0:  # pragma: no cover - runs in the child
        os.close(read_fd)
        signal.alarm(_CHILD_TIMEOUT_S)
        try:
            report = probe()
        except BaseException as exc:
            report = f"error: {exc!r}"
        os.write(write_fd, report.encode())
        os._exit(0)
    os.close(write_fd)
    with os.fdopen(read_fd, "rb") as pipe:
        report = pipe.read().decode()
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status), f"child died with status {status}"
    return report


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_a_forked_child_builds_its_own_client(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A16: only Metron dropped its clients in the child."""
    get_or_build = _SOURCES[name](tmp_path, monkeypatch)
    parent_client = get_or_build()
    assert get_or_build() is parent_client  # shared in the parent

    def probe() -> str:
        inherited = get_or_build() is parent_client
        return f"inherited={inherited} parent_closed={parent_client.close_calls}"

    assert _in_child(probe) == "inherited=False parent_closed=0"
    assert get_or_build() is parent_client  # the parent's entry is untouched


def test_a_prefetch_lock_held_at_the_fork_is_free_in_the_child() -> None:
    """
    A16: Metron's prefetch lock was inherited, possibly held.

    The thread that held it at the fork does not exist in the child, so
    the child would wait for it forever. Held here by the parent itself,
    which leaves the child the same state.
    """
    with metron._prefetch_lock:
        report = _in_child(lambda: f"prefetched={metron._has_prefetch(1)}")
    assert report == "prefetched=False"


def test_a_registry_lock_held_at_the_fork_is_free_in_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same for each shared-client registry's own lock."""
    getters = {name: make(tmp_path, monkeypatch) for name, make in _SOURCES.items()}
    locks = (metron._sessions.lock, metron._gates.lock)
    locks += (comicvine._sessions.lock, versedb._clients.lock)
    for lock in locks:
        lock.acquire()
    try:
        report = _in_child(
            lambda: " ".join(
                f"{name}={type(get()).__name__}"
                for name, get in sorted(getters.items())
            )
        )
    finally:
        for lock in locks:
            lock.release()
    assert report == "comicvine=_Client metron=_Client versedb=_Client"


def test_a_registry_warns_once_when_settings_differ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First build wins; a differing caller is told, once, and reuses it."""
    from loguru import logger as loguru_logger

    from comicbox.formats.base.online import warn_once
    from comicbox.formats.base.online.shared_clients import SharedClients

    monkeypatch.setattr(warn_once, "_seen", set())

    registry: SharedClients[str, _Client] = SharedClients("fake", "fake client")
    first = registry.get_or_build("k", ("a",), _Client)
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        again = registry.get_or_build("k", ("b",), _Client)
        registry.get_or_build("k", ("b",), _Client)
    finally:
        loguru_logger.remove(handler_id)
    assert again is first
    assert len(messages) == 1
    assert "reusing the existing shared fake client" in messages[0]


def test_an_unusable_client_is_rebuilt() -> None:
    from comicbox.formats.base.online.shared_clients import SharedClients

    registry: SharedClients[str, _Client] = SharedClients("fake", "fake client")
    first = registry.get_or_build("k", (), _Client)
    first.closed = True
    second = registry.get_or_build("k", (), _Client, reusable=lambda c: not c.closed)
    assert second is not first
    assert registry.get("k") is second
