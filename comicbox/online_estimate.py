"""
Estimate the API-request count and wall-clock for a batch online-tag run.

A batch caller (Codex) shows this to an operator before a "Tag Online" run
and mirrors it in a live countdown. Keeping the model here — next to the
search flow it describes and the rate limits it divides by — means the
numbers move with comicbox's behavior instead of drifting in a downstream
copy.

The model is deliberately simple. Per comic, each source costs a
characteristic number of API requests:

- Metron resolves an issue with a single ``issues_list`` search plus the
  final issue fetch — a flat count (see v4.0.5 / PR #143; no
  series-discovery step since series ids land directly on issue-list
  results). Metron does not fan out, so effort does not move it.
- Comic Vine discovers volumes, asks each surviving candidate for its
  issues, then fetches the issue it accepts. Only the middle step varies:
  ``Effort`` decides how many candidates are worth a call.

Match mode is not an input. It decides how a verdict is applied, never how
many requests a search spends.

Under first-match-wins a comic stops at the first source that answers, so
the run is billed the costliest single selected source; merging all sources
(``first_wins=False``) queries every source per comic, so their per-comic
costs are summed.

Wall-clock paces each source at its sustained throughput: Metron's
per-minute cap binds a bounded run directly. Comic Vine limits **per
resource pool** — 200/hour for each endpoint (simyan keeps a separate
bucket per endpoint, mirroring CV's documented "200 requests per resource
per hour") — so a run is bound by its busiest single pool, not by the
request total: discovery and the final fetches each land in their own pool
while the per-volume issue lookups stack in one. first-match-wins means a
comic isn't done until the binding source answers, so the slowest source
sets the pace; merging pays every source per comic, so their paces sum.

The projection prices a cold search for every comic. A real run batches by
series, where one search answers for the whole series and the issues after
it cost about one issue-list call each, so a library finishes ahead of this
number. Each call counted here is one HTTP request: simyan 4.1.0 stops
paginating on a short page, so a Comic Vine list call no longer spends two
of its pool's hourly budget (Simyan#309, see ``tasks/simyan-4-plan.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from comicbox.config.online.settings import Effort
from comicbox.formats.base.online.rate_limits import (
    COMICVINE_DEFAULT_PER_HOUR,
    METRON_DEFAULT_PER_MINUTE,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = (
    "COMICVINE_DISCOVERY_REQUESTS",
    "COMICVINE_FETCH_REQUESTS",
    "COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT",
    "DEFAULT_RATE_PER_MINUTE",
    "DEFAULT_REQUESTS_PER_COMIC",
    "METRON_REQUESTS_PER_COMIC",
    "SOURCE_RATE_PER_MINUTE",
    "RunEstimate",
    "estimate_run",
    "requests_per_comic",
)

# Sustained requests/minute used to pace a bounded run. Metron's per-minute
# cap binds directly. Comic Vine's entry is the 200/hour cap of ONE resource
# pool spread over the minute (rather than its 1/second burst) — see
# ``_seconds_per_comic`` for how a run draws on it. Derived from
# ``rate_limits`` so both move together.
SOURCE_RATE_PER_MINUTE: Final = MappingProxyType(
    {
        "metron": METRON_DEFAULT_PER_MINUTE,
        "comicvine": COMICVINE_DEFAULT_PER_HOUR // 60,
    }
)

# API requests one comic costs against Metron: the search and the issue
# fetch. Metron has no fan-out to throttle, so effort does not move it.
METRON_REQUESTS_PER_COMIC: Final[int] = 2

# Comic Vine's cold search, in three parts. Discovery is one
# ``search_volumes``, plus one narrowed ``list_volumes`` when the comic
# names a year. The issue it accepts then costs a ``get_issue`` and a
# ``get_volume``. Each of those four lands in its own resource pool.
COMICVINE_DISCOVERY_REQUESTS: Final[int] = 2
COMICVINE_FETCH_REQUESTS: Final[int] = 2

# The middle part, and the only one effort moves: how many surviving volume
# candidates are worth an issue-list call. They all stack in one pool, which
# makes this number the pace of a Comic Vine run as well as the bulk of its
# cost. Anchored to a measured cold search — mean 3.48 ``list_issues`` calls
# with the name filter off — scaled by the call reductions ``series_filter``
# records for each threshold (balanced -18%, minimal -60.5%) and rounded.
# Thorough rounds up so the unbounded search stays above balanced's filtered
# one. The measurement is in
# ``tasks/online-tagging/calibration-notes/2026-09-08-estimator-cold-search-cost.md``.
COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT: Final = MappingProxyType(
    {
        Effort.MINIMAL.value: 1,
        Effort.BALANCED.value: 3,
        Effort.THOROUGH.value: 4,
    }
)

# Fallbacks for an unrecognized source. An unrecognized effort is priced as
# ``balanced``, the shipped default.
DEFAULT_REQUESTS_PER_COMIC: Final[int] = 3
DEFAULT_RATE_PER_MINUTE: Final[int] = 10


@dataclass(frozen=True, slots=True)
class RunEstimate:
    """The projected cost of a batch online-tag run."""

    requests: int
    """Total API requests the run is expected to make."""
    seconds: float
    """Projected wall-clock duration in seconds."""


def _comicvine_issue_list_requests(effort: str) -> int:
    """Return the issue-list calls one Comic Vine search spends at ``effort``."""
    return COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT.get(
        effort, COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT[Effort.BALANCED.value]
    )


def requests_per_comic(source: str, effort: str = Effort.BALANCED.value) -> int:
    """
    Return the API requests one comic costs against ``source`` at ``effort``.

    ``effort`` is an :class:`~comicbox.config.online.settings.Effort` or its
    value. Resolve it for the source it prices —
    ``resolve_effort(settings.online, "comicvine")`` — because a per-source
    override beats the global setting.
    """
    if source == "metron":
        return METRON_REQUESTS_PER_COMIC
    if source == "comicvine":
        return (
            COMICVINE_DISCOVERY_REQUESTS
            + _comicvine_issue_list_requests(effort)
            + COMICVINE_FETCH_REQUESTS
        )
    return DEFAULT_REQUESTS_PER_COMIC


def _seconds_per_comic(source: str, effort: str) -> float:
    """
    Return the seconds one comic costs against ``source`` at its sustained pace.

    Comic Vine paces per resource pool, so its wall-clock cost is the busiest
    pool's share of the comic's requests over that pool's rate — not the
    request total. The per-volume issue lookups are that pool; everything
    else a comic spends sits alone in its own. Metron's per-minute cap paces
    the total directly.
    """
    if source == "comicvine":
        pool_requests = _comicvine_issue_list_requests(effort)
        return 60.0 * pool_requests / SOURCE_RATE_PER_MINUTE[source]
    rate = SOURCE_RATE_PER_MINUTE.get(source, DEFAULT_RATE_PER_MINUTE)
    return 60.0 * requests_per_comic(source, effort) / rate


def estimate_run(
    comics: int,
    sources: Sequence[str],
    *,
    effort: str = Effort.BALANCED.value,
    merge_all_sources: bool = False,
) -> RunEstimate:
    """
    Project the request count and wall-clock seconds for a batch online-tag run.

    ``comics`` is how many comics remain to look up and ``sources`` the
    enabled source names in priority order. ``effort`` is an
    :class:`~comicbox.config.online.settings.Effort` value (``"balanced"``
    etc.), resolved for the source it prices. ``merge_all_sources`` mirrors
    ``first_wins=False``: every source is queried per comic and their
    per-comic costs summed, instead of stopping at the first match.

    The projection assumes the effort it is handed. A CLI run can
    auto-engage a lower Comic Vine effort for a large unattended batch,
    which this cannot see.
    """
    sources = tuple(sources)
    if comics <= 0 or not sources:
        return RunEstimate(requests=0, seconds=0.0)
    per_source = [requests_per_comic(source, effort) for source in sources]
    # Merge sums every source's per-comic cost; first-match-wins bills the
    # costliest single source the run might hit.
    per_comic = sum(per_source) if merge_all_sources else max(per_source)
    requests = comics * per_comic
    # Merge pays every source per comic; first-match-wins isn't done until
    # the binding (slowest) source answers.
    paces = [_seconds_per_comic(source, effort) for source in sources]
    seconds_per_comic = sum(paces) if merge_all_sources else max(paces)
    return RunEstimate(requests=requests, seconds=comics * seconds_per_comic)
