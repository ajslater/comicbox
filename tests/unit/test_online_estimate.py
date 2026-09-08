"""Unit tests for the batch online-tag run estimator."""

from __future__ import annotations

import pytest

from comicbox.config.online.settings import Effort
from comicbox.online_estimate import (
    COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT,
    METRON_REQUESTS_PER_COMIC,
    SOURCE_RATE_PER_MINUTE,
    RunEstimate,
    estimate_run,
    requests_per_comic,
)

MINIMAL = Effort.MINIMAL.value
BALANCED = Effort.BALANCED.value
THOROUGH = Effort.THOROUGH.value


def test_rates_track_documented_limits() -> None:
    """The estimate rates derive from the documented per-source caps."""
    # Metron's per-minute cap; Comic Vine's 200/hour cap spread over the minute.
    assert SOURCE_RATE_PER_MINUTE["metron"] == 20
    assert SOURCE_RATE_PER_MINUTE["comicvine"] == 3


def test_zero_comics_is_empty() -> None:
    """No comics means no requests and no time."""
    assert estimate_run(0, ("metron",)) == RunEstimate(requests=0, seconds=0.0)


def test_no_sources_is_empty() -> None:
    """No enabled sources means no requests and no time."""
    assert estimate_run(10, ()) == RunEstimate(requests=0, seconds=0.0)


def test_metron_balanced() -> None:
    """Metron's flat two-step search: 10 comics x 2 requests / 20 per-minute."""
    est = estimate_run(10, ("metron",))
    assert est.requests == 20
    assert est.seconds == 60.0


def test_metron_requests_are_effort_independent() -> None:
    """Metron does not fan out, so no effort changes its two-step count."""
    estimates = [estimate_run(10, ("metron",), effort=e.value) for e in Effort]
    assert len(set(estimates)) == 1
    assert estimates[0].requests == 20


def test_comicvine_requests_scale_with_effort() -> None:
    """Effort bounds Comic Vine's fan-out, which is most of what a comic costs."""
    minimal = estimate_run(10, ("comicvine",), effort=MINIMAL)
    balanced = estimate_run(10, ("comicvine",), effort=BALANCED)
    thorough = estimate_run(10, ("comicvine",), effort=THOROUGH)
    # 10 x (2 discovery + fan-out + 2 fetch).
    assert minimal.requests == 50
    assert balanced.requests == 70
    assert thorough.requests == 80
    # Wall-clock tracks the issue-list pool alone, over the 3/min per-pool
    # rate: 10 x 60 x fan-out / 3.
    assert minimal.seconds == pytest.approx(200.0)
    assert balanced.seconds == pytest.approx(600.0)
    assert thorough.seconds == pytest.approx(800.0)


def test_more_effort_costs_more() -> None:
    """Both halves of the estimate rise with effort, in order."""
    estimates = [
        estimate_run(10, ("comicvine",), effort=e)
        for e in (MINIMAL, BALANCED, THOROUGH)
    ]
    requests = [est.requests for est in estimates]
    seconds = [est.seconds for est in estimates]
    assert requests == sorted(requests)
    assert seconds == sorted(seconds)
    assert len(set(requests)) == len(set(seconds)) == len(Effort)


def test_every_effort_is_priced() -> None:
    """No Effort member may fall through to the fallback."""
    for effort in Effort:
        assert effort.value in COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT


def test_comicvine_pacing_binds_on_busiest_pool_not_total() -> None:
    """
    Simyan paces per resource pool (CV's per-resource limit).

    Discovery and the accept fetch each sit alone in their own pool, so
    they cost requests without costing time; only the issue-list fan-out
    stacks, and it alone sets the pace.
    """
    est = estimate_run(10, ("comicvine",), effort=BALANCED)
    fan_out = COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT[BALANCED]
    assert est.requests == 10 * (fan_out + 4)
    assert est.seconds == pytest.approx(10 * 60.0 * fan_out / 3)


def test_slowest_source_binds_the_rate() -> None:
    """
    Comic Vine is slower than Metron and binds the pace.

    First-match-wins bills the costliest source's requests
    (max(metron 2, comicvine 7) = 7) and the slowest source's pace
    (comicvine: 60s x 3 pool requests / 3-per-minute = 60s/comic).
    """
    est = estimate_run(10, ("metron", "comicvine"))
    assert est.requests == 70
    assert est.seconds == pytest.approx(600.0)


def test_merge_sums_per_source_requests() -> None:
    """Merging queries every source per comic: requests and paces both sum."""
    est = estimate_run(10, ("metron", "comicvine"), merge_all_sources=True)
    assert est.requests == 90  # 10 x (metron 2 + comicvine 7)
    # 10 x (metron 6s + comicvine 60s)
    assert est.seconds == pytest.approx(660.0)


def test_merge_single_source_is_noop() -> None:
    """With one source there is nothing to merge, so the estimate is unchanged."""
    first_wins = estimate_run(10, ("metron",))
    merged = estimate_run(10, ("metron",), merge_all_sources=True)
    assert merged == first_wins


def test_default_effort_is_balanced() -> None:
    """Omitting the effort prices the shipped default."""
    assert estimate_run(10, ("comicvine",)) == estimate_run(
        10, ("comicvine",), effort=BALANCED
    )


def test_unknown_effort_is_priced_as_balanced() -> None:
    """An effort this version doesn't know falls back to the default."""
    assert estimate_run(10, ("comicvine",), effort="bogus") == estimate_run(
        10, ("comicvine",), effort=BALANCED
    )


def test_unknown_source_uses_defaults() -> None:
    """Unknown source -> 3 requests/comic and the 10/min default rate."""
    est = estimate_run(10, ("unknown",))
    assert est.requests == 30  # 10 x 3 default
    assert est.seconds == 180.0  # 30 / 10 default per-minute


def test_requests_per_comic_helper() -> None:
    """The per-source per-comic request count is exposed directly."""
    assert requests_per_comic("metron", THOROUGH) == METRON_REQUESTS_PER_COMIC
    assert requests_per_comic("comicvine", MINIMAL) == 5
    assert requests_per_comic("comicvine") == 7
    assert requests_per_comic("unknown") == 3
