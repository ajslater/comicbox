"""
Rate limits for online sources, with per-source overrides.

The upstream libraries (mokkari for Metron, simyan for ComicVine) already
enforce sensible rate limits via `pyrate_limiter`'s SQLite-backed bucket
that persists state across runs. Comicbox normally inherits those defaults
without intervention.

This module exists so:

1. The numbers are visible in our codebase (rather than hidden in
   transitive dependencies) and can be cited / audited.
2. Power users with higher API tiers can raise the cap without forking
   their library install — `online.<source>.rate_limit.*` config keys
   construct a custom bucket / limiter.
3. We can lower the cap defensively if a source ever publishes a stricter
   policy and we need to ship a release before the upstream library
   bumps its constants.

Defaults match the upstream-library values as of 2026-05. If they ever
disagree, the upstream library wins for the un-overridden case (we read
its value at session-construction time rather than passing our own).

Sources:
- Metron: 20 req/min, 5,000 req/day per IP
  https://metron.cloud/ — see also mokkari/session.py
- ComicVine: 1 req/sec, 200 req/hr per IP
  https://comicvine.gamespot.com/api/documentation — see simyan/comicvine.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSourceLimits


# Documented defaults for citation / audit. Upstream libraries enforce these
# automatically; we only construct our own buckets when overrides are set.
METRON_DEFAULT_PER_MINUTE: Final[int] = 20
METRON_DEFAULT_PER_DAY: Final[int] = 5_000
COMICVINE_DEFAULT_PER_SECOND: Final[int] = 1
COMICVINE_DEFAULT_PER_HOUR: Final[int] = 200


def build_metron_bucket(limits: OnlineSourceLimits | None):
    """
    Construct a custom mokkari bucket from override values, or None.

    Returns None when no overrides are set so mokkari uses its default
    SQLite-backed bucket (preserving cross-process / cross-run state). When
    any override is set, returns a fresh `SQLiteBucket` configured with the
    per-minute and per-day rates.

    Lazy-imports `pyrate_limiter` so callers without the override don't pay
    the import cost at module load.
    """
    if limits is None or (limits.per_minute is None and limits.per_day is None):
        return None
    from pyrate_limiter import Duration, Rate, SQLiteBucket

    rates = [
        Rate(limits.per_minute or METRON_DEFAULT_PER_MINUTE, Duration.MINUTE),
        Rate(limits.per_day or METRON_DEFAULT_PER_DAY, Duration.DAY),
    ]
    return SQLiteBucket.init_from_file(rates)


def build_comicvine_limiter(limits: OnlineSourceLimits | None):
    """
    Construct a custom simyan limiter from override values, or None.

    Returns None when no overrides are set so simyan uses its default. When
    any override is set, returns a fresh `Limiter` over a `SQLiteBucket`
    configured with the per-second and per-hour rates.
    """
    if limits is None or (limits.per_second is None and limits.per_hour is None):
        return None
    from pyrate_limiter import Duration, Limiter, Rate, SQLiteBucket

    rates = [
        Rate(limits.per_second or COMICVINE_DEFAULT_PER_SECOND, Duration.SECOND),
        Rate(limits.per_hour or COMICVINE_DEFAULT_PER_HOUR, Duration.HOUR),
    ]
    return Limiter(SQLiteBucket.init_from_file(rates))
