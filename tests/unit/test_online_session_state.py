"""Tests for the single owner of the mutable online lookup policy."""

from __future__ import annotations

import threading

from comicbox.config import get_config
from comicbox.config.online.settings import (
    MatchMode,
    OnlineLookupSettings,
    Prompts,
)
from comicbox.formats.base.online.session_state import (
    LookupPolicy,
    OnlineSessionState,
)


def _online():
    return get_config().online


def test_from_lookup_seeds_both_fields() -> None:
    lookup = OnlineLookupSettings(match=MatchMode.EAGER, prompts=Prompts.NEVER)
    policy = OnlineSessionState.from_lookup(lookup).snapshot()
    assert policy.match is MatchMode.EAGER
    assert policy.prompts is Prompts.NEVER


def test_unattended_is_derived_from_prompts() -> None:
    assert LookupPolicy(MatchMode.AUTO, Prompts.NEVER).unattended is True
    assert LookupPolicy(MatchMode.AUTO, Prompts.ASK).unattended is False


def test_setters_move_only_their_own_field() -> None:
    state = OnlineSessionState(match=MatchMode.AUTO, prompts=Prompts.ASK)
    state.set_match(MatchMode.CAREFUL)
    assert state.snapshot() == LookupPolicy(MatchMode.CAREFUL, Prompts.ASK)
    state.set_prompts(Prompts.NEVER)
    assert state.snapshot() == LookupPolicy(MatchMode.CAREFUL, Prompts.NEVER)
    # Unattended is reversible, unlike the one-way prompt action.
    state.set_prompts(Prompts.ASK)
    assert state.snapshot().unattended is False


def test_overlay_replaces_the_policy_and_nothing_else() -> None:
    online = _online()
    overlaid = OnlineSessionState(match=MatchMode.EAGER, prompts=Prompts.NEVER).overlay(
        online
    )
    assert overlaid.lookup.match is MatchMode.EAGER
    assert overlaid.lookup.prompts is Prompts.NEVER
    # Sibling blocks are carried over untouched, not rebuilt.
    assert overlaid.auth is online.auth
    # And nothing else moved: overlay the original policy back onto the
    # result and the whole tree compares equal again.
    restored = OnlineSessionState.from_lookup(online.lookup).overlay(overlaid)
    assert restored == online


def test_overlay_does_not_mutate_its_input() -> None:
    online = _online()
    before = online.lookup
    OnlineSessionState(match=MatchMode.EAGER, prompts=Prompts.NEVER).overlay(online)
    assert online.lookup is before
    assert online.lookup.match is before.match


def test_concurrent_readers_and_writers_see_only_written_values() -> None:
    """
    Reading while other threads write yields real values, never garbage.

    Both fields come out of one lock acquisition, so a reader can't catch
    a `set_match` half-applied. What two independent setter calls can't
    promise is that the *pair* came from one writer — the box makes one
    change per prompt action, so that's not a case the code produces.
    """
    pairs = [
        (MatchMode.CAREFUL, Prompts.ASK),
        (MatchMode.EAGER, Prompts.NEVER),
    ]
    state = OnlineSessionState(*pairs[0])
    barrier = threading.Barrier(3)
    stop = threading.Event()
    seen: list[LookupPolicy] = []
    errors: list[BaseException] = []

    def writer(match: MatchMode, prompts: Prompts) -> None:
        try:
            barrier.wait()
            while not stop.is_set():
                state.set_match(match)
                state.set_prompts(prompts)
        except BaseException as exc:
            errors.append(exc)

    def reader() -> None:
        try:
            barrier.wait()
            seen.extend(state.snapshot() for _ in range(2000))
        except BaseException as exc:
            errors.append(exc)
        finally:
            stop.set()

    threads = [threading.Thread(target=writer, args=pair) for pair in pairs]
    threads.append(threading.Thread(target=reader))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    assert seen
    written_matches = {match for match, _ in pairs}
    written_prompts = {prompts for _, prompts in pairs}
    assert all(policy.match in written_matches for policy in seen)
    assert all(policy.prompts in written_prompts for policy in seen)
