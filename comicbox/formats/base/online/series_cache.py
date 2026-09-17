"""
Thread-safe series cache for series-first batching (plan §3.10).

Maps ``(source_name, series_fingerprint)`` to the resolved upstream
volume/series id, so the second and later issues of a series skip the
cold-path candidate search and ask the source directly for "issue N in
volume V".

The population rule is FIRST WRITER WINS: a falsy-group collision (two
unrelated comics that happened to share a fingerprint) must never
overwrite an already-resolved entry. Expressing that as ``if key in
cache: return`` followed by ``cache[key] = value`` is fine for the
sequential caller (``OnlineSession.tag_many``) but races once the CLI's
``-j N`` thread pool drives it: two workers can both pass the membership
test and both claim to be the first writer, emitting two
``SeriesIdentified`` events for one series.

``SeriesCache`` closes that by making the claim a single locked
operation. It stays a plain ``MutableMapping`` so callers that just want
a dict — and the tests that pass one — keep working unchanged.
"""

from __future__ import annotations

import threading
from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Final

from loguru import logger
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SeriesCacheKey = tuple[str, str]


def filename_series_fingerprint(path: Path) -> str:
    """
    Lightweight series fingerprint derived from the filename alone.

    Lets a batch dispatcher cluster same-series comics together *before*
    opening any archives, so the first issue of each cluster pays for the
    cold-path search and the rest read the resolved volume id back out of
    the cache. Both dispatchers use it: `OnlineSession.tag_many` and the
    CLI's `Runner`.

    Falls back to the bare filename when comicfn2dict can't extract a
    series — those files won't benefit from batching but won't break it
    either (they sort to a deterministic "by filename" bucket).

    Deliberately mirrors `_series_fingerprint`'s component choice (see
    comicbox/box/online_lookup.py): the per-issue year is excluded,
    because clustering by it would scatter a multi-year run into one
    cluster per year and hand the cache a fresh cold path for each — the
    opposite of what the clustering is for. The volume ordinal is kept,
    since that is what separates reboots.
    """
    from comicfn2dict import comicfn2dict

    try:
        parsed = comicfn2dict(path.name)
    except Exception:  # pragma: no cover — comicfn2dict is permissive
        return path.name.lower()
    series = str(parsed.get("series") or "").strip().lower()
    volume = str(parsed.get("volume") or "").strip()
    return f"{series}|{volume}" if series else f"~{path.name.lower()}"


class SeriesCache(MutableMapping[SeriesCacheKey, int]):
    """
    A ``dict`` of resolved volume ids with an atomic first-writer claim.

    Also arbitrates SINGLE-FLIGHT resolution of a series. Sorting a batch
    by series fingerprint makes the cache hit for the second and later
    issues of a run — but only once the first one has finished, and a
    ``-j N`` pool starts the first N files of a cluster at the same
    instant. All N then miss, and all N pay for the cold search: the
    batching saves nothing for exactly the files it was added for.

    So one caller per key LEADS and the rest WAIT for it, then re-read
    the cache and take the cheap volume-scoped path. A leader that
    resolves nothing (no match, prompt declined, source failure) hands
    leadership to the next waiter rather than stranding the cluster.
    """

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[SeriesCacheKey, int] = {}
        self._lock = threading.Lock()
        # Keys currently being resolved, each with the event its waiters
        # block on. Absent key == nobody is resolving it.
        self._leaders: dict[SeriesCacheKey, threading.Event] = {}

    def claim(self, key: SeriesCacheKey, volume_id: int) -> bool:
        """
        Populate `key` and return True only if this caller was the first.

        The membership test and the insert happen under one lock, so
        exactly one concurrent caller is told it won — which is what the
        ``SeriesIdentified`` event and the first-writer-wins contract
        both rely on.
        """
        with self._lock:
            if key in self._data:
                return False
            self._data[key] = volume_id
            return True

    def lead(self, key: SeriesCacheKey) -> bool:
        """
        Claim the right to resolve `key`; True when this caller must do it.

        False means another caller is already resolving it and this one
        should `wait`. Resolved keys also return False — there is nothing
        left to lead. A leader MUST call `release` in a ``finally``, or
        its waiters hold until their timeout.
        """
        with self._lock:
            if key in self._data or key in self._leaders:
                return False
            self._leaders[key] = threading.Event()
            return True

    def wait(self, key: SeriesCacheKey, timeout: float) -> bool:
        """
        Block until the current leader of `key` releases, or `timeout`.

        Returns True when a leader released within the timeout. Either
        way the caller must re-read the cache: a leader can finish
        without resolving anything.
        """
        with self._lock:
            event = self._leaders.get(key)
        if event is None:
            return False
        return event.wait(timeout)

    def release(self, key: SeriesCacheKey) -> None:
        """Finish leading `key` and wake everyone waiting on it."""
        with self._lock:
            event = self._leaders.pop(key, None)
        if event is not None:
            event.set()

    def snapshot(self) -> dict[SeriesCacheKey, int]:
        """Return a consistent copy. Useful for persistence."""
        with self._lock:
            return dict(self._data)

    @override
    def __getitem__(self, key: SeriesCacheKey) -> int:
        """Return the resolved volume id for `key`."""
        with self._lock:
            return self._data[key]

    @override
    def __setitem__(self, key: SeriesCacheKey, value: int) -> None:
        """Set `key`, overwriting. Prefer `claim` for first-writer-wins."""
        with self._lock:
            self._data[key] = value

    @override
    def __delitem__(self, key: SeriesCacheKey) -> None:
        """Drop `key`."""
        with self._lock:
            del self._data[key]

    @override
    def __iter__(self) -> Iterator[SeriesCacheKey]:
        """Iterate a snapshot, so mutation during iteration is safe."""
        return iter(self.snapshot())

    @override
    def __len__(self) -> int:
        """Count the resolved series."""
        with self._lock:
            return len(self._data)

    @override
    def __contains__(self, key: object) -> bool:
        """Membership test."""
        with self._lock:
            return key in self._data


# How long a worker waits for another to resolve the series they share.
#
# Bounds one pathological case: a leader wedged on a slow source or an
# unanswered prompt must not hold its whole cluster hostage. Generous on
# purpose — the wait is what saves the cluster's other members a cold
# search each, and a leader blocked at the rate gate behind a rejection
# can legitimately take a minute. On timeout the waiter falls back to the
# cold search it would have done anyway, so overshooting costs latency
# and undershooting costs API budget.
SERIES_LEAD_TIMEOUT_S: Final[float] = 120.0


def lead_series(
    cache: MutableMapping[SeriesCacheKey, int], key: SeriesCacheKey
) -> bool:
    """
    Claim the right to resolve `key`, on any MutableMapping.

    False for a mapping without the single-flight API — a plain dict from
    a sequential caller, which has nothing to race. A True caller MUST
    pair this with `release_series` in a ``finally``.
    """
    lead = getattr(cache, "lead", None)
    return bool(lead(key)) if lead is not None else False


def release_series(
    cache: MutableMapping[SeriesCacheKey, int], key: SeriesCacheKey
) -> None:
    """Hand leadership of `key` back, on any MutableMapping."""
    release = getattr(cache, "release", None)
    if release is not None:
        release(key)


def await_series_leader(
    cache: MutableMapping[SeriesCacheKey, int],
    key: SeriesCacheKey,
    timeout: float = SERIES_LEAD_TIMEOUT_S,
) -> None:
    """
    Block while another caller resolves `key`, if one is.

    Returns as soon as there is no leader to wait for, which is also the
    plain-dict case. The caller re-reads the cache either way: a leader
    can finish without having resolved anything.
    """
    wait = getattr(cache, "wait", None)
    if wait is None or wait(key, timeout):
        return
    logger.debug(
        f"online: gave up waiting {timeout:.0f}s for the series leader of "
        f"{key[1]!r}; searching independently"
    )


def claim_series(
    cache: MutableMapping[SeriesCacheKey, int], key: SeriesCacheKey, volume_id: int
) -> bool:
    """
    First-writer-wins population that works on any MutableMapping.

    Uses `SeriesCache.claim` when the mapping provides it (the concurrent
    case) and falls back to check-then-set for a plain dict, which is all
    a single-threaded caller needs.
    """
    claim = getattr(cache, "claim", None)
    if claim is not None:
        return bool(claim(key, volume_id))
    if key in cache:
        return False
    cache[key] = volume_id
    return True
