"""
Estimate the API-request count and wall-clock for a batch online-tag run.

A batch caller (Codex) shows this to an operator before a "Tag Online" run
and mirrors it in a live countdown. Keeping the model here — next to the
search flow it describes and the rate limits it divides by — means the
numbers move with comicbox's behavior instead of drifting in a downstream
copy.

The model is deliberately simple. Per comic, each source costs a
characteristic number of API requests:

- Metron is a fixed two-step search (``series_list`` + ``issues_list``) —
  one or two requests — that match mode does not change (see v4.0.5).
- Comic Vine's fuzzy volume→issue path does more verification the tighter
  the match mode, so its request count scales with mode.

Under first-match-wins a comic stops at the first source that answers, so
the run is billed the costliest single selected source; merging all sources
(``first_wins=False``) queries every source per comic, so their per-comic
costs are summed.

Wall-clock is that request total over the slowest enabled source's sustained
throughput: Metron's per-minute cap binds a bounded run directly, while
Comic Vine's hourly cap is the real ceiling for any run longer than a few
minutes, so it is spread over the minute (see ``rate_limits``). first-match-
wins means a comic isn't done until the binding source answers, so the
slowest source sets the pace.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from comicbox.config.settings import MatchMode
from comicbox.formats.base.online.rate_limits import (
    COMICVINE_DEFAULT_PER_HOUR,
    METRON_DEFAULT_PER_MINUTE,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = (
    "COMICVINE_REQUESTS_BY_MODE",
    "DEFAULT_RATE_PER_MINUTE",
    "DEFAULT_REQUESTS_PER_COMIC",
    "METRON_REQUESTS_PER_COMIC",
    "SOURCE_RATE_PER_MINUTE",
    "RunEstimate",
    "estimate_run",
    "requests_per_comic",
)

# Sustained requests/minute used to pace a bounded run. Metron's per-minute
# cap binds directly; Comic Vine's 200/hour cap is the real ceiling for any
# run longer than a few minutes, so we spread it over the minute rather than
# use its 1/second burst. Derived from ``rate_limits`` so both move together.
SOURCE_RATE_PER_MINUTE: Final = MappingProxyType(
    {
        "metron": METRON_DEFAULT_PER_MINUTE,
        "comicvine": COMICVINE_DEFAULT_PER_HOUR // 60,
    }
)

# API requests one comic costs, per source. Metron's two-step search is a
# flat count match mode does not change; Comic Vine's scales with match mode.
METRON_REQUESTS_PER_COMIC: Final[int] = 2
COMICVINE_REQUESTS_BY_MODE: Final = MappingProxyType(
    {
        MatchMode.EAGER.value: 2,
        MatchMode.AUTO.value: 3,
        MatchMode.CAREFUL.value: 5,
    }
)

# Fallbacks for an unrecognized source / match mode.
DEFAULT_REQUESTS_PER_COMIC: Final[int] = 3
DEFAULT_RATE_PER_MINUTE: Final[int] = 10


@dataclass(frozen=True, slots=True)
class RunEstimate:
    """The projected cost of a batch online-tag run."""

    requests: int
    """Total API requests the run is expected to make."""
    seconds: float
    """Projected wall-clock duration in seconds."""


def requests_per_comic(source: str, mode: str) -> int:
    """Return the API requests one comic costs against ``source`` under ``mode``."""
    if source == "metron":
        return METRON_REQUESTS_PER_COMIC
    if source == "comicvine":
        return COMICVINE_REQUESTS_BY_MODE.get(mode, DEFAULT_REQUESTS_PER_COMIC)
    return DEFAULT_REQUESTS_PER_COMIC


def _slowest_rate_per_minute(sources: tuple[str, ...]) -> int:
    rates = [SOURCE_RATE_PER_MINUTE[s] for s in sources if s in SOURCE_RATE_PER_MINUTE]
    return min(rates) if rates else DEFAULT_RATE_PER_MINUTE


def estimate_run(
    comics: int,
    mode: str,
    sources: Sequence[str],
    *,
    merge_all_sources: bool = False,
) -> RunEstimate:
    """
    Project the request count and wall-clock seconds for a batch online-tag run.

    ``comics`` is how many comics remain to look up, ``mode`` a
    :class:`~comicbox.config.settings.MatchMode` value (``"auto"`` etc.), and
    ``sources`` the enabled source names in priority order. ``merge_all_sources``
    mirrors ``first_wins=False``: every source is queried per comic and their
    per-comic costs summed, instead of stopping at the first match.
    """
    sources = tuple(sources)
    if comics <= 0 or not sources:
        return RunEstimate(requests=0, seconds=0.0)
    per_source = [requests_per_comic(source, mode) for source in sources]
    # Merge sums every source's per-comic cost; first-match-wins bills the
    # costliest single source the run might hit.
    per_comic = sum(per_source) if merge_all_sources else max(per_source)
    requests = comics * per_comic
    minutes = requests / _slowest_rate_per_minute(sources)
    return RunEstimate(requests=requests, seconds=minutes * 60.0)
