"""
Rate limits for online sources, with per-source overrides.

The upstream libraries (mokkari for Metron, simyan for ComicVine) already
enforce sensible rate limits via `pyrate_limiter`'s SQLite-backed bucket
that persists state across runs. Comicbox inherits Metron's default
without intervention; for ComicVine it always installs its own limiter
(see below).

This module exists so:

1. The numbers are visible in our codebase (rather than hidden in
   transitive dependencies) and can be cited / audited.
2. Power users with higher API tiers can raise the cap without forking
   their library install — `online.<source>.rate_limit.*` config keys
   construct a custom bucket / limiter.
3. We can lower the cap defensively if a source ever publishes a stricter
   policy and we need to ship a release before the upstream library
   bumps its constants.
4. ComicVine specifically: simyan's limiter blocks *indefinitely* on an
   hourly-cap hit (`try_acquire(timeout=-1)`), which reads as a silent,
   uninterruptible hang. We always wrap it so the blocking wait is
   bounded and long waits surface as `RateLimitError` through comicbox's
   logged, cancellable retry layer — see `build_comicvine_limiter` /
   `_BoundedComicVineLimiter`. (mokkari already raises on its local cap,
   so Metron needs no such wrapper.)

Defaults match the upstream-library values as of 2026-05. For Metron's
un-overridden case the upstream library's bucket is used (we read its
value at session-construction time rather than passing our own).

Sources:
- Metron: 20 req/min, 5,000 req/day per IP
  https://metron.cloud/ — see also mokkari/session.py
- ComicVine: 1 req/sec, 200 req/hr per IP
  https://comicvine.gamespot.com/api/documentation — see simyan/comicvine.py
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Final

from typing_extensions import override

if TYPE_CHECKING:
    from pathlib import Path

    from comicbox.config.settings import OnlineSourceLimits


# Documented defaults for citation / audit. Upstream libraries enforce these
# automatically; we only construct our own buckets when overrides are set.
METRON_DEFAULT_PER_MINUTE: Final[int] = 20
METRON_DEFAULT_PER_DAY: Final[int] = 5_000
COMICVINE_DEFAULT_PER_SECOND: Final[int] = 1
COMICVINE_DEFAULT_PER_HOUR: Final[int] = 200

# Ceiling on how long simyan's client-side limiter may block *in-process*
# before we raise and hand the wait to comicbox's retry layer (see
# `_BoundedComicVineLimiter`). It must sit above the worst-case
# 1-request/second pacing wait — which under `-j N` parallel contention on
# the shared SQLite bucket stacks to roughly N seconds — so normal
# throughput is never penalised; and well below the 200/hour cap's
# recovery time (minutes), so an hourly-cap hit reliably trips it. 15s
# covers the documented `-j 8` workflow with margin while keeping the
# silent in-limiter block short enough to stay responsive to Ctrl-C /
# cancel(). Lower it for tighter cancellation latency, raise it for very
# high `-j`.
COMICVINE_LOCAL_WAIT_CEILING_S: Final[float] = 15.0

# Override buckets/limiters memoized per (source, db_path, rates) for the
# life of the process. Sessions are rebuilt per API call and sources per
# file, so without memoization every call would start a brand-new bucket
# (with no db_path, pyrate_limiter even creates a fresh temp sqlite file
# per call) and the configured limit would never accumulate state — the
# override would silently not limit anything.
_override_cache: dict[tuple, Any] = {}
_override_lock = threading.Lock()


def build_metron_bucket(limits: OnlineSourceLimits | None, db_path: Path | str):
    """
    Construct a custom mokkari bucket from override values, or None.

    Returns None when no overrides are set so mokkari uses its default
    SQLite-backed bucket (preserving cross-process / cross-run state). When
    any override is set, returns a process-wide memoized `SQLiteBucket`
    persisted at ``db_path`` with the per-minute and per-day rates.

    Lazy-imports `pyrate_limiter` so callers without the override don't pay
    the import cost at module load.
    """
    if limits is None or (limits.per_minute is None and limits.per_day is None):
        return None
    from pyrate_limiter import Duration, Rate, SQLiteBucket

    key = ("metron", str(db_path), limits.per_minute, limits.per_day)
    with _override_lock:
        if key not in _override_cache:
            rates = [
                Rate(limits.per_minute or METRON_DEFAULT_PER_MINUTE, Duration.MINUTE),
                Rate(limits.per_day or METRON_DEFAULT_PER_DAY, Duration.DAY),
            ]
            _override_cache[key] = SQLiteBucket.init_from_file(
                rates, db_path=str(db_path)
            )
        return _override_cache[key]


# Lazily-defined, process-wide cache for the bounded limiter subclass.
# Holds 0 or 1 element; the class is defined on first use so importing this
# module never pulls in `pyrate_limiter` (see module docstring). A list
# doubles as the memo and is cheap to guard under `_override_lock`.
_bounded_limiter_cls: list[type] = []


def _bounded_comicvine_limiter_cls() -> type:
    """
    Lazily define + cache the `Limiter` subclass that bounds the blocking wait.

    Defined inside a function so the `pyrate_limiter` import stays lazy
    (the class can't be declared at module level without importing its
    base). Tests reach the class through this accessor.
    """
    with _override_lock:
        if not _bounded_limiter_cls:
            from pyrate_limiter import Limiter

            class _BoundedComicVineLimiter(Limiter):
                """
                simyan `Limiter` that caps the client-side blocking wait.

                simyan's transport calls ``limiter.try_acquire(name)`` with
                pyrate_limiter's defaults — ``blocking=True, timeout=-1``
                (wait forever). When the persistent 200-request/hour bucket
                fills, that wait stretches toward a full hour of silent
                ``time.sleep`` deep in pyrate_limiter: no log line, and
                comicbox's cancellable retry layer (which only engages on a
                *raised* exception) never runs. Ctrl-C is the only escape,
                and a library caller's ``cancel()`` is powerless.

                This subclass bounds the in-limiter wait to
                ``wait_ceiling_s``: short waits (the 1-request/second
                pacing, even under ``-j`` parallel contention) are absorbed
                transparently as before; a longer wait means the hourly cap
                was hit, so we raise simyan's ``RateLimitError`` and hand the
                wait to comicbox's ``@with_retry`` layer instead — logged,
                bounded by ``_RATE_LIMIT_SCHEDULE``, and cancellable wherever
                a caller wired ``retry_sleep`` (CLI Ctrl-C; OnlineSession
                cancel event). This makes ComicVine behave like Metron,
                whose mokkari client already raises ``RateLimitError`` on
                local-bucket exhaustion.
                """

                def __init__(self, bucket: Any, *, wait_ceiling_s: float) -> None:
                    super().__init__(bucket)
                    self._wait_ceiling_s = wait_ceiling_s

                @override
                def try_acquire(
                    self,
                    name: str = "pyrate",
                    weight: int = 1,
                    blocking: bool = True,
                    timeout: float = -1,
                ) -> Any:
                    # simyan's transport calls us with the pyrate defaults
                    # (blocking=True, timeout=-1 = wait forever) — that's the
                    # path we bound. Defer unchanged to the base for any
                    # explicit timeout / non-blocking request so we stay a
                    # faithful override.
                    if not blocking or timeout != -1:
                        return super().try_acquire(
                            name, weight=weight, blocking=blocking, timeout=timeout
                        )
                    # A finite timeout makes pyrate sleep at most
                    # wait_ceiling_s, then return False instead of blocking
                    # indefinitely.
                    if super().try_acquire(
                        name,
                        weight=weight,
                        blocking=True,
                        timeout=self._wait_ceiling_s,
                    ):
                        return True
                    from simyan.errors import RateLimitError

                    msg = (
                        "comicvine: client-side rate limit reached after "
                        f"waiting {self._wait_ceiling_s:.0f}s for a slot "
                        "(200 requests/hour cap); deferring the wait to "
                        "comicbox's retry/backoff layer"
                    )
                    raise RateLimitError(msg)

            _bounded_limiter_cls.append(_BoundedComicVineLimiter)
        return _bounded_limiter_cls[0]


def build_comicvine_limiter(limits: OnlineSourceLimits | None, db_path: Path | str):
    """
    Construct comicbox's ComicVine limiter (always non-None).

    Returns a process-wide memoized `_BoundedComicVineLimiter` over a
    `SQLiteBucket` persisted at ``db_path``. Override values from
    ``online.comicvine.rate_limit.*`` set the per-second / per-hour rates;
    absent overrides fall back to the documented CV defaults (1/sec,
    200/hr — the same numbers simyan ships).

    Unlike `build_metron_bucket`, this never returns None: we always
    install our own limiter so the blocking wait is *bounded*. simyan's
    default limiter calls ``try_acquire`` with ``timeout=-1`` (wait
    forever), turning an hourly-cap hit into a silent, uninterruptible
    multi-minute block. Wrapping the limiter is the only lever —
    pyrate_limiter 4.x dropped ``max_delay`` from the `Limiter`
    constructor, and simyan's transport hardcodes the ``try_acquire`` call
    args. See `_BoundedComicVineLimiter` for the bounding behaviour.
    """
    from pyrate_limiter import Duration, Rate, SQLiteBucket

    per_second = COMICVINE_DEFAULT_PER_SECOND
    per_hour = COMICVINE_DEFAULT_PER_HOUR
    if limits is not None:
        per_second = limits.per_second or per_second
        per_hour = limits.per_hour or per_hour

    # Resolve the class *before* taking _override_lock: the accessor takes
    # the same (non-reentrant) lock, so calling it while held would deadlock.
    limiter_cls = _bounded_comicvine_limiter_cls()
    key = ("comicvine", str(db_path), per_second, per_hour)
    with _override_lock:
        if key not in _override_cache:
            rates = [
                Rate(per_second, Duration.SECOND),
                Rate(per_hour, Duration.HOUR),
            ]
            bucket = SQLiteBucket.init_from_file(rates, db_path=str(db_path))
            _override_cache[key] = limiter_cls(
                bucket, wait_ceiling_s=COMICVINE_LOCAL_WAIT_CEILING_S
            )
        return _override_cache[key]
