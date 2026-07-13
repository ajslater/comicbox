"""Unit tests for the batch online-tag run estimator."""

from __future__ import annotations

import pytest

from comicbox.online_estimate import (
    COMICVINE_REQUESTS_BY_MODE,
    METRON_REQUESTS_PER_COMIC,
    SOURCE_RATE_PER_MINUTE,
    RunEstimate,
    estimate_run,
    requests_per_comic,
)


def test_rates_track_documented_limits() -> None:
    """The estimate rates derive from the documented per-source caps."""
    # Metron's per-minute cap; Comic Vine's 200/hour cap spread over the minute.
    assert SOURCE_RATE_PER_MINUTE["metron"] == 20
    assert SOURCE_RATE_PER_MINUTE["comicvine"] == 3


def test_zero_comics_is_empty() -> None:
    """No comics means no requests and no time."""
    assert estimate_run(0, "auto", ("metron",)) == RunEstimate(requests=0, seconds=0.0)


def test_no_sources_is_empty() -> None:
    """No enabled sources means no requests and no time."""
    assert estimate_run(10, "auto", ()) == RunEstimate(requests=0, seconds=0.0)


def test_metron_auto() -> None:
    """Metron's flat two-step search: 10 comics x 2 requests / 20 per-minute."""
    est = estimate_run(10, "auto", ("metron",))
    assert est.requests == 20
    assert est.seconds == 60.0


def test_metron_requests_are_mode_independent() -> None:
    """Match mode does not change Metron's fixed two-step request count."""
    auto = estimate_run(10, "auto", ("metron",))
    careful = estimate_run(10, "careful", ("metron",))
    eager = estimate_run(10, "eager", ("metron",))
    assert auto == careful == eager
    assert auto.requests == 20


def test_comicvine_requests_scale_with_mode() -> None:
    """Comic Vine's per-comic requests scale with match mode; pacing per pool."""
    careful = estimate_run(10, "careful", ("comicvine",))
    eager = estimate_run(10, "eager", ("comicvine",))
    assert careful.requests == 50  # 10 x 5
    assert eager.requests == 20  # 10 x 2
    # Wall-clock tracks the busiest resource pool (careful 2, eager 1) over
    # the 3/min per-pool rate, not the request total.
    assert careful.seconds == pytest.approx(400.0)  # 10 x 60 x 2/3
    assert eager.seconds == pytest.approx(200.0)  # 10 x 60 x 1/3


def test_comicvine_pacing_binds_on_busiest_pool_not_total() -> None:
    """
    Simyan 3.x paces per resource pool (CV's per-resource limit).

    Auto costs more requests than eager, but the extras land in different
    pools, so both sustain the same pace.
    """
    eager = estimate_run(10, "eager", ("comicvine",))
    auto = estimate_run(10, "auto", ("comicvine",))
    assert auto.requests > eager.requests
    assert auto.seconds == eager.seconds


def test_slowest_source_binds_the_rate() -> None:
    """
    Comic Vine is slower than Metron and binds the pace.

    First-match-wins bills the costliest source's requests
    (max(metron 2, comicvine 3) = 3) and the slowest source's pace
    (comicvine: 60s x 1-pool-request / 3-per-minute = 20s/comic).
    """
    est = estimate_run(10, "auto", ("metron", "comicvine"))
    assert est.requests == 30
    assert est.seconds == pytest.approx(200.0)


def test_merge_sums_per_source_requests() -> None:
    """Merging queries every source per comic: requests and paces both sum."""
    est = estimate_run(10, "auto", ("metron", "comicvine"), merge_all_sources=True)
    assert est.requests == 50  # 10 x (metron 2 + comicvine 3)
    # 10 x (metron 6s + comicvine 20s)
    assert est.seconds == pytest.approx(260.0)


def test_merge_single_source_is_noop() -> None:
    """With one source there is nothing to merge, so the estimate is unchanged."""
    first_wins = estimate_run(10, "auto", ("metron",))
    merged = estimate_run(10, "auto", ("metron",), merge_all_sources=True)
    assert merged == first_wins


def test_unknown_mode_and_source_use_defaults() -> None:
    """Unknown mode -> 3 requests/comic; unknown source -> 10/min default rate."""
    est = estimate_run(10, "bogus", ("unknown",))
    assert est.requests == 30  # 10 x 3 default
    assert est.seconds == 180.0  # 30 / 10 default per-minute


def test_requests_per_comic_helper() -> None:
    """The per-source per-comic request count is exposed directly."""
    assert requests_per_comic("metron", "careful") == METRON_REQUESTS_PER_COMIC
    assert requests_per_comic("comicvine", "auto") == COMICVINE_REQUESTS_BY_MODE["auto"]
    assert requests_per_comic("unknown", "auto") == 3
