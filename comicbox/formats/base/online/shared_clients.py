"""
Process-wide API clients, one per credential set, shared by every source.

Sources are rebuilt per file (`_build_active_online_sources` in
comicbox/box/online_lookup.py), so a client memoized on the source alone
gave every comic of a batch its own connection pool and cache handle.
Each online source keeps its clients in a `SharedClients` registry at
module scope instead, which every file and every worker thread of
`Runner._run_parallel`'s pool reuses.

Contract: FIRST BUILD WINS. A client, and the response cache baked into
it, is built from the settings of whichever source instance misses
first; a later source with the same credentials reuses it even if its
own cache settings differ, and is warned once. Keying by cache settings
instead would split one token's rate-limit state across clients.
Entries are never evicted: a registry is bounded by the credential sets
one process uses. How a client is closed stays each source's business.

Fork safety lives here, once for every registry. A pooled HTTP session
and a sqlite connection must not be shared across a fork (codex's
`multiprocessing` librarian and `comicbox/process.py`'s pool are the
forks), so a forked child drops every entry, without closing it, as the
parent is still using those sockets. Each lock is rebound rather than
taken: a thread that held one at the instant of the fork does not exist
in the child, so acquiring it there would wait forever.
"""

from __future__ import annotations

import os
import threading
import weakref
from typing import TYPE_CHECKING, Generic, TypeVar

from comicbox.formats.base.online.warn_once import warn_once

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

K = TypeVar("K", bound="Hashable")
C = TypeVar("C")

_registries: weakref.WeakSet[SharedClients] = weakref.WeakSet()
_fork_callbacks: list[Callable[[], None]] = []


class SharedClients(Generic[K, C]):
    """One source's shared clients, keyed by credential set."""

    def __init__(self, source: str, noun: str) -> None:
        """Name the source and what it shares, for the mismatch warning."""
        self._source = source
        self._noun = noun
        self._entries: dict[K, tuple[C, tuple]] = {}
        self.lock = threading.Lock()
        _registries.add(self)

    def get_or_build(
        self,
        key: K,
        signature: tuple,
        build: Callable[[], C],
        *,
        reusable: Callable[[C], bool] | None = None,
    ) -> C:
        """
        Return the client for ``key``, building it on the first miss.

        ``signature`` is the settings a built client bakes in; a later
        caller whose signature differs is warned once and handed the
        built client. ``reusable`` says whether a cached client can still
        send; one that cannot is rebuilt in its place. ``build`` runs
        under the registry's lock, so two threads never build one key.
        """
        with self.lock:
            entry = self._entries.get(key)
            if entry is None or (reusable is not None and not reusable(entry[0])):
                client = build()
                self._entries[key] = (client, signature)
                return client
        client, built_signature = entry
        if built_signature != signature:
            warn_once(
                f"{self._source}:session-config-mismatch",
                f"online {self._source}: reusing the existing shared "
                f"{self._noun}; this instance's differing cache settings "
                f"{signature} are ignored in favor of its {built_signature}",
            )
        return client

    def get(self, key: K) -> C | None:
        """Return the client for ``key``, or None if none was built."""
        with self.lock:
            entry = self._entries.get(key)
        return entry[0] if entry else None

    def keys(self) -> tuple[K, ...]:
        """Snapshot the credential sets with a client."""
        with self.lock:
            return tuple(self._entries)

    def clients(self) -> tuple[C, ...]:
        """Snapshot every client, leaving the entries in place."""
        with self.lock:
            return tuple(client for client, _ in self._entries.values())

    def drain(self) -> tuple[C, ...]:
        """Remove every entry and return its client, for the caller to close."""
        with self.lock:
            clients = tuple(client for client, _ in self._entries.values())
            self._entries.clear()
        return clients

    def _forget_in_child(self) -> None:
        """Drop every entry unclosed and rebind the lock. Fork handler only."""
        self.lock = threading.Lock()
        self._entries.clear()


def on_fork_in_child(callback: Callable[[], None]) -> None:
    """
    Run ``callback`` in a forked child, after the registries are dropped.

    For a source's other module state that a child must not inherit as
    is, such as a lock of its own.
    """
    _fork_callbacks.append(callback)


def _after_fork_in_child() -> None:
    """Drop every registry's clients and rebind every lock in the child."""
    for registry in tuple(_registries):
        registry._forget_in_child()  # noqa: SLF001
    for callback in _fork_callbacks:
        callback()


if hasattr(os, "register_at_fork"):  # POSIX only
    os.register_at_fork(after_in_child=_after_fork_in_child)
