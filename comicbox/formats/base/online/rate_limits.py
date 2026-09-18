"""
Rate limits for online sources, for citation / audit.

Neither upstream library takes a local override: mokkari reads Metron's
per-user limits off the `X-RateLimit-*` response headers, and simyan
builds its ComicVine limiter internally with no injection point at all.
This module exists so the numbers are visible in our codebase (rather
than hidden in transitive dependencies) and can be cited / audited, and
so the consumers below have a stable constant to work from.

These are STARTING POINTS, not the enforced values. Metron's real limits
arrive in `X-RateLimit-Burst-Limit` / `X-RateLimit-Sustained-Limit` on
every response, 429s included, and `RateGate` switches to the reported
numbers as soon as the first response lands — a donor tier raises the
daily window, and a self-hosted instance may not throttle at all. The
constant below is only what the gate paces at before it has been told.

Sources:
- Metron: the burst window is `DEFAULT_THROTTLE_RATES["burst"]` in the
  server's settings. 20/minute is the documented floor and the only
  figure Metron's maintainer will commit to publishing; production
  commonly reports 45-60 and is dialled back toward 20 on peak days. So
  the constant below is a floor to start at, never a ceiling to assume,
  and the header is authoritative in both directions — the gate adopts a
  drop as readily as a rise. The daily sustained limit starts at
  5,000/day and is raised for OpenCollective donors (up to 25,000/day),
  so there is no constant to cite for it.
  https://metron.cloud/ — see also mokkari/session.py
- ComicVine: 1 req/sec, 200 req/hr per IP
  https://comicvine.gamespot.com/api/documentation — see simyan/comicvine.py
"""

from __future__ import annotations

from typing import Final

# Metron's documented burst floor. Two jobs, both of them provisional:
# the pace `RateGate` uses before any response has arrived, and the
# estimator's fallback for a source no gate has talked to yet. It is NOT
# a lower bound on either — `source_rate_per_minute` prefers the live
# gate's reported limit, and a self-hosted instance that reports 10 is
# both paced and priced at 10. See the module docstring: the header
# wins the moment one arrives, upward or downward.
METRON_DEFAULT_PER_MINUTE: Final[int] = 20
# simyan enforces these internally (hardcoded literals, no importable
# constant), so these are the only place the numbers appear by name.
# Two consumers read the hourly cap: `online_estimate` derives its pacing
# math from it, and the ComicVine source subtracts spent bucket rows from
# it to report a remaining budget.
COMICVINE_DEFAULT_PER_SECOND: Final[int] = 1
COMICVINE_DEFAULT_PER_HOUR: Final[int] = 200
