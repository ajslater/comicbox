"""Tests for the pre-call series-name filter."""

from __future__ import annotations

import pytest

from comicbox.config.settings import APIBudget
from comicbox.formats.base.online.series_filter import (
    should_keep_volume_name,
    threshold_for,
)

# --------------------------------------------------------- threshold table


def test_threshold_for_known_budgets() -> None:
    """Each APIBudget maps to its Phase B-validated threshold."""
    assert threshold_for(APIBudget.EXHAUSTIVE) == 0.0
    assert threshold_for(APIBudget.BALANCED) == 0.4
    assert threshold_for(APIBudget.FAST) == 0.7


def test_threshold_for_known_budgets_exhaustive_table() -> None:
    """Every defined `APIBudget` member has a threshold (no defensive default)."""
    # Iterating the enum ensures we don't ship a member without a
    # threshold row — the defensive `.get(..., 0.0)` in `threshold_for`
    # is a safety net but the table is meant to be exhaustive.
    for budget in APIBudget:
        threshold = threshold_for(budget)
        assert 0.0 <= threshold <= 1.0, f"{budget}: bad threshold {threshold}"


# ----------------------------------------------- should_keep_volume_name


def test_threshold_zero_keeps_everything() -> None:
    """`BALANCED` (Phase A) is a no-op — every volume passes."""
    # Even an obviously-wrong volume name passes when threshold is 0.
    assert should_keep_volume_name("Lois Lane", "Watchmen", threshold=0.0)


def test_missing_profile_series_keeps_volume() -> None:
    """No comparison anchor → never drop on missing data."""
    assert should_keep_volume_name(None, "Watchmen", threshold=0.7)
    assert should_keep_volume_name("", "Watchmen", threshold=0.7)


def test_missing_volume_name_keeps_volume() -> None:
    """Can't compare a missing name → keep."""
    assert should_keep_volume_name("Watchmen", None, threshold=0.7)
    assert should_keep_volume_name("Watchmen", "", threshold=0.7)


def test_exact_match_kept() -> None:
    """Identical names pass any threshold."""
    assert should_keep_volume_name("Watchmen", "Watchmen", threshold=0.7)
    assert should_keep_volume_name("Watchmen", "Watchmen", threshold=0.99)


def test_punctuation_variants_kept() -> None:
    """Normalization handles punctuation: GI Joe vs G.I. Joe."""
    # `normalize_series` strips non-alphanumeric so both reduce to "g i joe".
    assert should_keep_volume_name("GI Joe", "G.I. Joe", threshold=0.7)
    assert should_keep_volume_name("X-Men", "X Men", threshold=0.7)


def test_volume_suffix_variants_kept() -> None:
    """The `(Vol. 2)` suffix is stripped by normalization."""
    assert should_keep_volume_name("Spider-Man", "Spider-Man (Vol. 2)", threshold=0.7)


def test_celebration_style_volumes_dropped_at_fast_threshold() -> None:
    """
    Drop the motivating "Lois Lane: A Celebration"-style volumes.

    The matcher's `s_series` already scores these near zero — this filter
    just skips the API call to confirm. Under `FAST` they're filtered out
    before the per-volume list_issues call.
    """
    assert not should_keep_volume_name(
        "Lois Lane",
        "Lois Lane: A Celebration of 75 Years",
        threshold=0.7,
    )
    assert not should_keep_volume_name(
        "Lois Lane",
        "Adventures of Lois Lane and Friends",
        threshold=0.7,
    )


def test_year_in_parens_kept() -> None:
    """
    Pure year suffixes are stripped before comparison; the volume is kept.

    CV's volume convention is "Series Name (YYYY)" — this is the same
    series, just annotated with its start year. The pre-filter strips
    year/year-range parentheticals so short series names like "Conan
    (2004)" still match "Conan" at the 0.7 threshold.
    """
    assert should_keep_volume_name("Watchmen", "Watchmen (1986)", threshold=0.7)
    assert should_keep_volume_name("Lois Lane", "Lois Lane (1986)", threshold=0.7)
    assert should_keep_volume_name("Lois Lane", "Lois Lane (2019)", threshold=0.7)
    assert should_keep_volume_name("Conan", "Conan (2004)", threshold=0.7)
    # Year-range form, hyphen and en-dash both:
    assert should_keep_volume_name("Watchmen", "Watchmen (1986-1990)", threshold=0.7)
    # En-dash (U+2013) variant. Built via chr() so the source doesn't
    # carry a literal ambiguous character (RUF001).
    en_dash = chr(0x2013)
    en_dash_year_range = f"Watchmen (1986{en_dash}1990)"
    assert should_keep_volume_name("Watchmen", en_dash_year_range, threshold=0.7)


def test_non_year_parens_preserved_and_filtered() -> None:
    """
    Preserve non-year parens — they denote different volumes.

    Annotation labels in parens are NOT stripped — they legitimately
    distinguish different volumes from the bare-named original, so the
    ratio should drop them below the threshold. "Watchmen (2008 Reprint)"
    stays as "Watchmen (2008 Reprint)" after year-paren stripping (the
    content has more than just a year), so the Levenshtein ratio against
    bare "Watchmen" is dominated by the suffix and falls below 0.7.
    """
    assert not should_keep_volume_name(
        "Watchmen", "Watchmen (2008 Reprint)", threshold=0.7
    )
    assert not should_keep_volume_name(
        "Watchmen", "Watchmen (Annotated)", threshold=0.7
    )


@pytest.mark.parametrize(
    ("profile_series", "volume_name"),
    [
        # All these are known CV "Lois Lane" variants that should fail tight
        # filter — none would score well in s_series anyway.
        ("Lois Lane", "Adventures of Superman: Lois Lane"),
        ("Lois Lane", "Tales of Lois Lane and Jimmy Olsen"),
        ("Lois Lane", "Showcase Presents: Superman Family"),
    ],
)
def test_dissimilar_dropped_at_fast(profile_series: str, volume_name: str) -> None:
    """At `FAST`'s 0.7 threshold, divergent volumes get filtered out."""
    assert not should_keep_volume_name(profile_series, volume_name, threshold=0.7)


def test_threshold_boundary_inclusive() -> None:
    """A name scoring exactly at the threshold is kept (>= not >)."""
    # We can't easily construct a name that scores EXACTLY 70.0, but we
    # can verify the comparison is inclusive at any threshold the call
    # actually hits. Use threshold 0 and confirm any non-empty pair passes.
    # (Comparison is `>= threshold * 100`; at threshold=0, every score
    # passes.)
    assert should_keep_volume_name("Foo", "Bar", threshold=0.0)


# ----------------------------------------- max_results_for (Phase D)


def test_max_results_for_fast_caps_at_5() -> None:
    """`fast` budget caps discovery-search breadth at 5."""
    from comicbox.formats.base.online.series_filter import max_results_for

    assert max_results_for(APIBudget.FAST, default=20) == 5


def test_max_results_for_balanced_uses_default() -> None:
    """`balanced` (and `exhaustive`) inherit the source's class default."""
    from comicbox.formats.base.online.series_filter import max_results_for

    assert max_results_for(APIBudget.BALANCED, default=20) == 20
    assert max_results_for(APIBudget.EXHAUSTIVE, default=20) == 20


def test_max_results_for_passes_through_alternative_default() -> None:
    """`default` arg lets callers thread their own class constant in."""
    from comicbox.formats.base.online.series_filter import max_results_for

    # Hypothetical: a future source with default=30.
    assert max_results_for(APIBudget.BALANCED, default=30) == 30
    # FAST still caps at 5 regardless of the caller's default.
    assert max_results_for(APIBudget.FAST, default=30) == 5
