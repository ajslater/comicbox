"""
Rate limits for online sources, with per-source overrides.

The upstream libraries (mokkari for Metron, simyan for ComicVine) enforce
sensible rate limits via SQLite-backed buckets that persist state across
runs. Comicbox inherits both libraries' defaults without intervention.

This module exists so:

1. The numbers are visible in our codebase (rather than hidden in
   transitive dependencies) and can be cited / audited.
2. Power users with higher Metron API tiers can raise the cap without
   forking their library install — `online.metron.rate_limit.*` config
   keys construct a custom mokkari bucket. (No ComicVine equivalent:
   simyan 3.x builds its limiter internally with no injection point and
   caps the blocking wait at `max_delay = timeout * 2`, so hourly-cap
   hits surface as errors for comicbox's retry layer instead of blocking
   forever. `online.comicvine.rate_limit.*` keys are accepted but
   ignored with a warning.)
3. We can lower the Metron cap defensively if the source ever publishes
   a stricter policy and we need to ship a release before mokkari bumps
   its constants.

Defaults match the upstream-library values as of 2026-07. For Metron's
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

if TYPE_CHECKING:
    from pathlib import Path

    from comicbox.config.settings import OnlineSourceLimits


# Documented defaults for citation / audit. mokkari enforces these
# automatically; we only construct our own bucket when overrides are set.
METRON_DEFAULT_PER_MINUTE: Final[int] = 20
METRON_DEFAULT_PER_DAY: Final[int] = 5_000
# simyan 3.x enforces these internally (hardcoded literals, no importable
# constant). Kept for citation; `online_estimate` derives its pacing math
# from the hourly cap.
COMICVINE_DEFAULT_PER_SECOND: Final[int] = 1
COMICVINE_DEFAULT_PER_HOUR: Final[int] = 200

# Override buckets memoized per (source, db_path, rates) for the life of
# the process. Sessions are rebuilt per API call and sources per file, so
# without memoization every call would start a brand-new bucket (with no
# db_path, pyrate_limiter even creates a fresh temp sqlite file per call)
# and the configured limit would never accumulate state — the override
# would silently not limit anything.
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
