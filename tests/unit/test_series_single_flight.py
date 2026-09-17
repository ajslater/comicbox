"""
Single-flight series resolution.

Sorting a batch by series fingerprint only pays off once the first file
of a cluster has finished. A `-j N` pool starts N files at the same
instant, so without arbitration all N miss the cache and all N pay for
the same cold search — the batching saves nothing for exactly the files
it was added for.
"""

from __future__ import annotations

import threading

from comicbox.formats.base.online.series_cache import SeriesCache

KEY = ("metron", "spider-man||2018|marvel")
OTHER = ("metron", "batman||2011|dc")


def test_one_caller_leads_and_the_rest_do_not() -> None:
    cache = SeriesCache()
    assert cache.lead(KEY) is True
    assert cache.lead(KEY) is False
    assert cache.lead(OTHER) is True


def test_release_hands_leadership_on() -> None:
    """
    A leader that resolved nothing must not strand its cluster.

    No match, a declined prompt and a source failure all end with the key
    unresolved. The next caller has to be able to take over, or every
    remaining file of that series waits out its timeout for a leader that
    is never coming back.
    """
    cache = SeriesCache()
    assert cache.lead(KEY) is True
    cache.release(KEY)
    assert cache.lead(KEY) is True


def test_a_resolved_key_has_nothing_left_to_lead() -> None:
    cache = SeriesCache()
    cache.claim(KEY, 42)
    assert cache.lead(KEY) is False


def test_waiters_block_until_the_leader_releases() -> None:
    cache = SeriesCache()
    assert cache.lead(KEY) is True
    woke = threading.Event()
    result: list[bool] = []

    def follower() -> None:
        result.append(cache.wait(KEY, timeout=5.0))
        woke.set()

    thread = threading.Thread(target=follower)
    thread.start()
    try:
        assert not woke.wait(0.1)  # still blocked on the leader
        cache.claim(KEY, 42)
        cache.release(KEY)
        assert woke.wait(5.0)
    finally:
        thread.join(timeout=5.0)
    assert result == [True]
    assert cache[KEY] == 42


def test_waiting_on_an_unled_key_returns_immediately() -> None:
    """Nobody is resolving it, so there is nothing to wait for."""
    cache = SeriesCache()
    assert cache.wait(KEY, timeout=5.0) is False


def test_wait_times_out_on_a_wedged_leader() -> None:
    """
    A leader that never releases must not hold its cluster forever.

    On timeout the waiter takes the cold path it would have taken
    anyway, so the bound costs API budget rather than correctness.
    """
    cache = SeriesCache()
    assert cache.lead(KEY) is True
    assert cache.wait(KEY, timeout=0.05) is False


def test_exactly_one_leader_under_contention() -> None:
    """The whole point, asserted with real threads."""
    cache = SeriesCache()
    started = threading.Barrier(8)
    leaders: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        started.wait()
        won = cache.lead(KEY)
        with lock:
            leaders.append(won)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert sum(leaders) == 1
    assert len(leaders) == 8
