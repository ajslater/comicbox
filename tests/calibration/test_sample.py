"""
Unit tests for the stratified fixture sampler.

The walk-and-extract path needs real comics, so those bits are covered by
the live-API calibration runs. These tests focus on the pure-Python
sampling logic: bucketing, dedup, round-robin stratification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.calibration.sample import (
    _UNKNOWN_DECADE,
    _UNKNOWN_PUBLISHER,
    _bucket_key,
    _coerce_int,
    _Comic,
    _decade_bucket,
    _dedupe_by_series,
    _stratified_sample,
    _summarize_buckets,
)


def _make(
    *,
    name: str,
    series: str,
    year: int | None = 2015,
    publisher: str = "Marvel",
    metron: int | None = 1,
    cv: int | None = 2,
) -> _Comic:
    return _Comic(
        file_path=Path(f"/lib/{name}.cbz"),
        series=series,
        publisher=publisher,
        year=year,
        metron_id=metron,
        cv_id=cv,
    )


# ----------------------------------------------------------- _coerce_int


def test_coerce_int_passthrough() -> None:
    assert _coerce_int(42) == 42


def test_coerce_int_string_digits() -> None:
    assert _coerce_int("42") == 42


def test_coerce_int_none() -> None:
    assert _coerce_int(None) is None


def test_coerce_int_unparseable() -> None:
    assert _coerce_int("forty-two") is None
    assert _coerce_int({"x": 1}) is None


# ----------------------------------------------------------- _decade_bucket


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        pytest.param(1939, "pre-1980", id="golden-age"),
        pytest.param(1979, "pre-1980", id="late-bronze"),
        pytest.param(1980, "1980s", id="1980-boundary"),
        pytest.param(1986, "1980s", id="watchmen"),
        pytest.param(1989, "1980s", id="late-80s"),
        pytest.param(1990, "1990s", id="1990-boundary"),
        pytest.param(2009, "2000s", id="late-2000s"),
        pytest.param(2010, "2010s", id="2010-boundary"),
        pytest.param(2019, "2010s", id="late-2010s"),
        pytest.param(2020, "2020s+", id="2020s"),
        pytest.param(2099, "2020s+", id="far-future"),
        pytest.param(None, _UNKNOWN_DECADE, id="missing"),
    ],
)
def test_decade_bucket(year: int | None, expected: str) -> None:
    assert _decade_bucket(year) == expected


# ----------------------------------------------------------- _dedupe_by_series


def test_dedupe_by_series_keeps_alphabetically_first() -> None:
    comics = [
        _make(name="Watchmen #003", series="Watchmen"),
        _make(name="Watchmen #001", series="Watchmen"),
        _make(name="Watchmen #002", series="Watchmen"),
    ]
    deduped = _dedupe_by_series(comics)
    assert len(deduped) == 1
    assert deduped[0].file_path.name == "Watchmen #001.cbz"


def test_dedupe_by_series_keeps_distinct_series() -> None:
    comics = [
        _make(name="Watchmen #001", series="Watchmen"),
        _make(name="Lois Lane #001", series="Lois Lane"),
    ]
    deduped = _dedupe_by_series(comics)
    assert {c.series for c in deduped} == {"Watchmen", "Lois Lane"}


def test_dedupe_by_series_empty_input() -> None:
    assert _dedupe_by_series([]) == []


# ----------------------------------------------------------- _bucket_key


def test_bucket_key_combines_decade_and_publisher() -> None:
    comic = _make(name="x", series="X", year=1986, publisher="DC")
    assert _bucket_key(comic) == ("1980s", "DC")


def test_bucket_key_unknown_decade_when_year_missing() -> None:
    comic = _make(name="x", series="X", year=None, publisher="DC")
    assert _bucket_key(comic) == (_UNKNOWN_DECADE, "DC")


# ----------------------------------------------------------- _stratified_sample


def test_stratified_sample_is_round_robin_balanced() -> None:
    """Two equal buckets, target=4 → sample is split 2-2."""
    marvel = [
        _make(name=f"m{i}", series=f"Marvel-{i}", year=2015, publisher="Marvel")
        for i in range(10)
    ]
    dc = [
        _make(name=f"d{i}", series=f"DC-{i}", year=2015, publisher="DC")
        for i in range(10)
    ]
    sampled = _stratified_sample(marvel + dc, target=4, seed=0)
    counts = _summarize_buckets(sampled)
    assert counts[("2010s", "Marvel")] == 2
    assert counts[("2010s", "DC")] == 2


def test_stratified_sample_respects_target() -> None:
    comics = [
        _make(name=f"c{i}", series=f"S-{i}", year=2015, publisher="Marvel")
        for i in range(50)
    ]
    assert len(_stratified_sample(comics, target=10, seed=0)) == 10


def test_stratified_sample_capped_by_bucket_union() -> None:
    """When target > all available comics, return everything (no padding)."""
    comics = [
        _make(name="a", series="A", year=2015, publisher="Marvel"),
        _make(name="b", series="B", year=2015, publisher="DC"),
    ]
    sampled = _stratified_sample(comics, target=100, seed=0)
    assert len(sampled) == 2


def test_stratified_sample_round_robins_uneven_buckets() -> None:
    """
    Big bucket (10 comics) + tiny bucket (2 comics), target=8.

    Round 1: 1 Marvel + 1 DC → 2 total.
    Round 2: 1 Marvel + 1 DC → 4 total.
    Round 3+: DC exhausted, Marvel continues alone → +1 per round.
    Round 6: 8 total. So Marvel = 6, DC = 2.
    """
    marvel = [
        _make(name=f"m{i}", series=f"Marvel-{i}", year=2015, publisher="Marvel")
        for i in range(10)
    ]
    dc = [
        _make(name=f"d{i}", series=f"DC-{i}", year=2015, publisher="DC")
        for i in range(2)
    ]
    sampled = _stratified_sample(marvel + dc, target=8, seed=0)
    counts = _summarize_buckets(sampled)
    assert counts[("2010s", "Marvel")] == 6
    assert counts[("2010s", "DC")] == 2


def test_stratified_sample_seed_reproducible() -> None:
    """Same seed → same sample. Different seeds may reorder."""
    comics = [
        _make(name=f"c{i}", series=f"S-{i}", year=2015, publisher="Marvel")
        for i in range(20)
    ]
    a = _stratified_sample(comics, target=5, seed=42)
    b = _stratified_sample(comics, target=5, seed=42)
    assert [c.file_path for c in a] == [c.file_path for c in b]


def test_stratified_sample_distinct_decades_get_separate_buckets() -> None:
    """A 1986 Marvel and a 2015 Marvel land in different buckets."""
    old = _make(name="o", series="Old", year=1986, publisher="Marvel")
    new = _make(name="n", series="New", year=2015, publisher="Marvel")
    sampled = _stratified_sample([old, new], target=2, seed=0)
    counts = _summarize_buckets(sampled)
    assert counts[("1980s", "Marvel")] == 1
    assert counts[("2010s", "Marvel")] == 1


def test_stratified_sample_unknown_publisher_groups_separately() -> None:
    """Comics missing a publisher land in their own bucket, not Marvel."""
    marvel = _make(name="m", series="M", year=2015, publisher="Marvel")
    unknown = _make(name="u", series="U", year=2015, publisher=_UNKNOWN_PUBLISHER)
    sampled = _stratified_sample([marvel, unknown], target=2, seed=0)
    counts = _summarize_buckets(sampled)
    assert counts[("2010s", "Marvel")] == 1
    assert counts[("2010s", _UNKNOWN_PUBLISHER)] == 1
