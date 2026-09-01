"""
One owner for the online session's mutable lookup policy.

Two settings change mid-run when a selector answers ``set_policy`` or
``set_unattended``: ``match`` and ``prompts``. Everything else in
``OnlineSettings`` is resolved once at config time and never moves.

This module owns that pair for the whole run. Readers take a
``snapshot()`` (both fields under one lock acquisition, so a concurrent
writer can't hand out a mixed pair) or an ``overlay()`` of an otherwise
static ``OnlineSettings``. A box takes exactly one overlay per lookup
and threads that frozen view down its call chain, so a file resolves
under a single consistent policy generation even while a sibling
``-j N`` worker is changing it; the change lands on the next file.

Deliberately a dumb holder: payload validation and the operator-facing
logging live in ``ComicboxOnlineLookup._apply_session_action``, which
has the source name for its messages.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace

from comicbox.config.online.settings import (
    MatchMode,
    OnlineLookupSettings,
    OnlineSettings,
    Prompts,
)


@dataclass(frozen=True, slots=True)
class LookupPolicy:
    """A consistent read of the session's mutable lookup policy."""

    match: MatchMode
    prompts: Prompts

    @property
    def unattended(self) -> bool:
        """Whether comicbox may not prompt."""
        return self.prompts is Prompts.NEVER


class OnlineSessionState:
    """Thread-safe owner of the two session-mutable lookup settings."""

    def __init__(self, match: MatchMode, prompts: Prompts) -> None:
        """Seed the policy from resolved config values."""
        self._lock = threading.Lock()
        self._match = match
        self._prompts = prompts

    @classmethod
    def from_lookup(cls, lookup: OnlineLookupSettings) -> OnlineSessionState:
        """Seed from a resolved lookup settings block."""
        return cls(match=lookup.match, prompts=lookup.prompts)

    def snapshot(self) -> LookupPolicy:
        """Read both fields as one consistent pair."""
        with self._lock:
            return LookupPolicy(match=self._match, prompts=self._prompts)

    def set_match(self, match: MatchMode) -> None:
        """Change the match mode for the rest of the run."""
        with self._lock:
            self._match = match

    def set_prompts(self, prompts: Prompts) -> None:
        """Change the prompting policy for the rest of the run."""
        with self._lock:
            self._prompts = prompts

    def overlay(self, online: OnlineSettings) -> OnlineSettings:
        """Project the live policy onto otherwise static online settings."""
        with self._lock:
            match = self._match
            prompts = self._prompts
        new_lookup = replace(online.lookup, match=match, prompts=prompts)
        return replace(online, lookup=new_lookup)
