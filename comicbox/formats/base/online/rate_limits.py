"""
Rate limits for online sources, for citation / audit.

Neither upstream library takes a local override anymore: mokkari>=4.0.1
tracks Metron's actual per-user limits from the `X-RateLimit-*` response
headers instead of a fixed local bucket (see `MetronOnlineSource`'s
`_warn_ignored_rate_limit_overrides`), and simyan builds its ComicVine
limiter internally with no injection point at all. This module exists so
the numbers are visible in our codebase (rather than hidden in transitive
dependencies) and can be cited / audited, and so the two consumers below
have a stable constant to work from.

Sources:
- Metron: 20 req/min burst, fixed for every user. The daily sustained
  limit starts at 5,000/day and is raised for OpenCollective donors (up
  to 25,000/day) — mokkari discovers the actual value per-user from
  response headers, so it's no longer a constant we can cite.
  https://metron.cloud/ — see also mokkari/session.py
- ComicVine: 1 req/sec, 200 req/hr per IP
  https://comicvine.gamespot.com/api/documentation — see simyan/comicvine.py
"""

from __future__ import annotations

from typing import Final

# Metron's burst limit is fixed for every user regardless of API tier, so
# this stays a citable constant. There is no equivalent constant for the
# daily sustained limit anymore — see the module docstring.
METRON_DEFAULT_PER_MINUTE: Final[int] = 20
# simyan enforces these internally (hardcoded literals, no importable
# constant), so these are the only place the numbers appear by name.
# Two consumers read the hourly cap: `online_estimate` derives its pacing
# math from it, and the ComicVine source subtracts spent bucket rows from
# it to report a remaining budget.
COMICVINE_DEFAULT_PER_SECOND: Final[int] = 1
COMICVINE_DEFAULT_PER_HOUR: Final[int] = 200
