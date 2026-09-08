"""
Online matcher tests: the signals and the metadata score built from them.

What the matcher does with the ranking — auto-write, prompt or skip,
tiebreaks, cover hashing — is in ``test_online_matcher_resolution``.
"""

from __future__ import annotations

import pytest

from comicbox.formats.base.online.matcher import (
    metadata_score,
)
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
    parse_issue_int,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.signals import (
    s_issue,
    s_pages,
    s_publisher,
    s_series,
    s_year,
)
from tests.util.online_matcher import make_candidate, make_profile

# --------------------------------------------------------- helpers


def test_parse_issue_int_strips_leading_zeros() -> None:
    assert parse_issue_int("001") == 1
    assert parse_issue_int("01") == 1
    assert parse_issue_int("5") == 5


def test_parse_issue_int_returns_none_for_non_numeric() -> None:
    assert parse_issue_int("1a") is None
    assert parse_issue_int("1.5") is None
    assert parse_issue_int("Special") is None
    assert parse_issue_int("") is None
    assert parse_issue_int(None) is None


def test_parse_year_extracts_4_digit() -> None:
    assert parse_year("2020-04-01") == 2020
    assert parse_year(2020) == 2020
    assert parse_year("Spring 2020") == 2020
    assert parse_year("no year here") is None
    assert parse_year(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("007", "7"),
        ("01", "1"),
        ("1", "1"),
        ("0", "0"),
        ("000", "0"),
        ("001a", "1a"),
        ("0a", "0a"),
        ("1.5", "1.5"),
        ("1/2", "1/2"),
        ("Special", "Special"),
        ("", ""),
        (None, None),
    ],
)
def test_strip_issue_leading_zeros(raw: str | None, expected: str | None) -> None:
    assert strip_issue_leading_zeros(raw) == expected


# --------------------------------------------------------- signals


class TestSeriesSignal:
    def test_exact_match_is_one(self) -> None:
        assert s_series(make_profile(), make_candidate()) == 1.0

    def test_volume_suffix_normalized(self) -> None:
        score = s_series(
            make_profile(series="Foo Comics"),
            make_candidate(series="Foo Comics (Vol. 2)"),
        )
        assert score >= 0.8

    def test_punctuation_normalized(self) -> None:
        score = s_series(
            make_profile(series="X-Men"),
            make_candidate(series="X Men"),
        )
        assert score >= 0.8

    def test_missing_either_side_zero(self) -> None:
        assert s_series(make_profile(series=None), make_candidate()) == 0.0
        assert s_series(make_profile(), make_candidate(series="")) == 0.0

    def test_alt_name_beats_primary_name(self) -> None:
        """A localized volume title matches on its alias."""
        score = s_series(
            make_profile(series="Attack on Titan"),
            make_candidate(
                series="Shingeki no Kyojin", alt_series=("Attack on Titan",)
            ),
        )
        assert score == 1.0

    def test_alt_name_cannot_lower_a_primary_match(self) -> None:
        score = s_series(
            make_profile(series="Foo Comics"),
            make_candidate(series="Foo Comics", alt_series=("Totally Unrelated",)),
        )
        assert score == 1.0

    def test_no_alt_names_scores_as_before(self) -> None:
        """Sources without aliases (Metron search) are unaffected."""
        assert s_series(make_profile(), make_candidate(alt_series=())) == s_series(
            make_profile(), make_candidate()
        )

    def test_missing_profile_zero_even_with_alt_names(self) -> None:
        score = s_series(
            make_profile(series=None), make_candidate(alt_series=("Foo Comics",))
        )
        assert score == 0.0

    def test_alt_names_only_still_scores(self) -> None:
        score = s_series(
            make_profile(series="Foo Comics"),
            make_candidate(series="", alt_series=("Foo Comics",)),
        )
        assert score == 1.0


class TestIssueSignal:
    def test_int_match_is_one(self) -> None:
        assert s_issue(make_profile(issue_int=5), make_candidate(issue="5")) == 1.0
        assert s_issue(make_profile(issue_int=5), make_candidate(issue="005")) == 1.0

    def test_int_mismatch_is_zero(self) -> None:
        assert s_issue(make_profile(issue_int=5), make_candidate(issue="6")) == 0.0

    def test_string_match_is_one(self) -> None:
        assert (
            s_issue(
                make_profile(issue_int=None, issue="1a"), make_candidate(issue="1a")
            )
            == 1.0
        )

    def test_missing_one_side_returns_partial_credit(self) -> None:
        score = s_issue(
            make_profile(issue=None, issue_int=None), make_candidate(issue="5")
        )
        assert score == 0.5


class TestYearSignal:
    def test_exact_year_one(self) -> None:
        assert s_year(make_profile(year=2020), make_candidate(year=2020)) == 1.0

    def test_off_by_one(self) -> None:
        assert s_year(make_profile(year=2020), make_candidate(year=2021)) == 0.7

    def test_off_by_two(self) -> None:
        assert s_year(make_profile(year=2020), make_candidate(year=2022)) == 0.4

    def test_off_by_three_decays_smoothly(self) -> None:
        """Phase F: diff=3 → 0.32 (was 0.0 under the original cliff)."""
        assert s_year(
            make_profile(year=2020), make_candidate(year=2023)
        ) == pytest.approx(0.32, abs=1e-9)

    def test_off_by_four_continues_decay(self) -> None:
        """Phase F: linear decay from diff=2 to diff=7."""
        assert s_year(
            make_profile(year=2020), make_candidate(year=2024)
        ) == pytest.approx(0.24, abs=1e-9)

    def test_off_by_six_near_cliff(self) -> None:
        """Phase F: diff=6 → 0.08, just before the cliff at diff=7."""
        assert s_year(
            make_profile(year=2020), make_candidate(year=2026)
        ) == pytest.approx(0.08, abs=1e-9)

    def test_off_by_seven_hits_cliff(self) -> None:
        """Phase F: diff=7 still hits 0.0 — the long tail doesn't get year credit."""
        assert s_year(make_profile(year=2020), make_candidate(year=2027)) == 0.0

    def test_far_off_zero(self) -> None:
        assert s_year(make_profile(year=2020), make_candidate(year=2010)) == 0.0

    def test_both_missing_weak_prior(self) -> None:
        """Symmetric missing (no info on either side) → 0.5 prior."""
        assert s_year(make_profile(year=None), make_candidate(year=None)) == 0.5

    def test_asymmetric_missing_partial(self) -> None:
        """
        One side has year, the other doesn't → 0.3.

        Lower than any real-match bracket (even ±2 → 0.4) to avoid
        over-crediting wrong-volume candidates whose BasicIssue search
        result happens to lack a cover_date.
        """
        assert s_year(make_profile(year=2020), make_candidate(year=None)) == 0.3
        assert s_year(make_profile(year=None), make_candidate(year=2020)) == 0.3


class TestPublisherSignal:
    def test_exact(self) -> None:
        assert (
            s_publisher(
                make_profile(publisher="Quality Comics"),
                make_candidate(publisher="Quality Comics"),
            )
            == 1.0
        )

    def test_normalized_match(self) -> None:
        assert (
            s_publisher(
                make_profile(publisher="Quality Comics, Inc."),
                make_candidate(publisher="quality"),
            )
            == 1.0
        )

    def test_different(self) -> None:
        assert (
            s_publisher(
                make_profile(publisher="DC"),
                make_candidate(publisher="Marvel"),
            )
            == 0.0
        )

    def test_missing(self) -> None:
        assert s_publisher(make_profile(publisher=None), make_candidate()) == 0.5


class TestPagesSignal:
    def test_exact(self) -> None:
        assert (
            s_pages(make_profile(page_count=24), make_candidate(page_count=24)) == 1.0
        )

    def test_within_10pct(self) -> None:
        assert (
            s_pages(make_profile(page_count=24), make_candidate(page_count=22)) == 0.7
        )

    def test_within_25pct(self) -> None:
        assert (
            s_pages(make_profile(page_count=24), make_candidate(page_count=20)) == 0.3
        )

    def test_far_off(self) -> None:
        assert (
            s_pages(make_profile(page_count=24), make_candidate(page_count=48)) == 0.0
        )


# --------------------------------------------------------- scoring


def test_perfect_match_scores_one() -> None:
    score = metadata_score(make_profile(), make_candidate())
    assert score == pytest.approx(1.0)


def test_wrong_issue_drops_score() -> None:
    score = metadata_score(make_profile(issue_int=5), make_candidate(issue="6"))
    # Issue weight is 0.25 / 0.80 = ~0.3125; missing it should drop to ~0.6875.
    assert 0.65 < score < 0.72


def test_partial_match_above_min_confidence() -> None:
    # Right series + issue, missing publisher + pages, year off by one.
    score = metadata_score(
        make_profile(publisher=None, page_count=None, year=2020),
        make_candidate(publisher=None, page_count=None, year=2021),
    )
    assert score >= 0.50


# ----------- Phase K: signal-content-aware metadata score


def test_phase_k_cv_basicissue_perfect_match_scores_one() -> None:
    """
    Thumbnail-library CV BasicIssue match scores 1.0 when both sides lack publisher / pages.

    The structural cap on CV BasicIssue candidates pre-Phase-K was
    md=0.91 (s_publisher=0.5 + s_pages=0.6 priors). The "Wolverine #20
    (2026)" prompt-UX issue was caused exactly by this cap when a
    thumbnail-only profile met a CV BasicIssue (both sides missing
    publisher + pages).

    Phase K rev 2: only signals where BOTH sides are missing are
    dropped. Asymmetric absence (profile has data, candidate doesn't)
    keeps the signal so its weak-prior value contributes. See the
    `asymmetric` tests below for that case.
    """
    score = metadata_score(
        make_profile(year=2026, publisher=None, page_count=None),
        make_candidate(year=2026, publisher=None, page_count=None),
    )
    # Three contributing signals (series, issue, year) at 1.0; publisher
    # and pages dropped because both sides are missing. Renormalised
    # score = (0.30 + 0.25 + 0.10) / (0.30 + 0.25 + 0.10) = 1.0.
    assert score == pytest.approx(1.0, abs=1e-9)


def test_phase_k_no_contribution_returns_zero() -> None:
    """
    Phase K: zero contributing signals (truly empty case) → 0.0.

    If neither profile nor candidate have any of the five signals,
    there's nothing to match on; return 0.0 rather than dividing by zero.
    """
    profile = ComicProfile(series=None, issue=None, issue_int=None)
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="",
            issue="",
            year=None,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
        ),
    )
    assert metadata_score(profile, cand) == 0.0


def test_phase_k_solo_signal_uses_full_weight() -> None:
    """
    One contributing signal → score is that signal's value.

    Edge case worth a test: if only series matches (no issue, year,
    etc. on either side), the renormalised score is just s_series.
    A perfect series match alone yields 1.0 — which is "trust the
    series name and nothing else." For solo-viable candidates, this
    interacts with Phase E's `solo_confidence_threshold` (default 0.95)
    which protects against silent auto-write here.
    """
    profile = ComicProfile(series="Foo Comics", issue=None, issue_int=None)
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="Foo Comics",
            issue="",
            year=None,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
        ),
    )
    # Only s_series contributes (1.0); renormalised score is 1.0.
    assert metadata_score(profile, cand) == pytest.approx(1.0, abs=1e-9)


def test_alt_names_alone_contribute_the_series_signal() -> None:
    """
    A candidate whose only series data is an alias still weighs W_SERIES.

    `s_series` scores alt names, so the contributing-signals gate has to
    count them as series data. Dropping the signal would take W_SERIES
    out of the renormalisation denominator and inflate the rest — the
    Phase K rev-1 bug class.
    """
    profile = ComicProfile(series="Foo Comics", issue=None, issue_int=None)
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="",
            issue="",
            year=None,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
            alt_series=("Foo Comics",),
        ),
    )
    assert metadata_score(profile, cand) == pytest.approx(1.0, abs=1e-9)


def test_phase_k_asymmetric_publisher_uses_weak_prior() -> None:
    """
    Profile has publisher but candidate doesn't → weak prior penalises.

    Phase K rev 1 dropped this signal from the denominator, which let CV
    BasicIssue candidates with missing publisher coast to perfect scores
    they didn't deserve. Phase K rev 2 keeps the signal in the
    denominator and lets s_publisher's 0.5 weak prior pull the score
    down — matching pre-Phase-K behaviour for asymmetric data.
    """
    score = metadata_score(
        make_profile(publisher="Marvel"),
        make_candidate(publisher=None),  # asymmetric: profile has, candidate doesn't
    )
    # All 5 signals contribute. Publisher weak prior 0.5, others 1.0.
    # Weighted sum: 0.75 (publisher contributes 0.10 * 0.5).
    # Total weight: 0.80 (full _METADATA_WEIGHT_SUM).
    # Renormalised: 0.75 / 0.80 → 0.9375.
    assert score == pytest.approx(0.9375, abs=1e-9)


def test_phase_k_asymmetric_year_penalises_candidate() -> None:
    """
    Profile has year, candidate has year=None → s_year=0.3 contributes.

    This is the Conan regression case: a CV BasicIssue with year=None
    (e.g. canonical "Conan the Barbarian" volume that doesn't expose its
    cover_date in the search response) should NOT score the same as a
    candidate that genuinely matches the profile's year. Phase K rev 1
    dropped the year signal entirely on asymmetric absence, which
    inverted the ranking for the bigmedia "Conan the Barbarian by Jim
    Zub: Land of the Lotus (2021)" fixture. Rev 2 keeps the signal and
    lets s_year's 0.3 asymmetric value penalise the under-informed
    candidate.
    """
    score = metadata_score(
        make_profile(year=2021),
        make_candidate(year=None),
    )
    # All 5 signals contribute. Year asymmetric penalty 0.3, others 1.0.
    # Weighted sum: 0.73 (year contributes 0.10 * 0.3).
    # Total weight: 0.80 (full _METADATA_WEIGHT_SUM).
    # Renormalised: 0.73 / 0.80 → 0.9125.
    assert score == pytest.approx(0.9125, abs=1e-9)


def test_phase_k_symmetric_missing_year_dropped_from_denominator() -> None:
    """
    Both sides missing year → signal dropped, denominator shrinks.

    The thumbnail-library complement to the asymmetric case: when
    neither side carries year (a barely-tagged comic against a CV
    BasicIssue that also lacks cover_date), there's genuinely nothing to
    compare. Drop the signal entirely so the other matching signals
    still produce a confident score.
    """
    score = metadata_score(
        make_profile(year=None),
        make_candidate(year=None),
    )
    # Year skipped (both None). Remaining 4 signals all at 1.0.
    # Weighted sum: 0.70.
    # Total weight: 0.70 (year's 0.10 dropped from denominator).
    # Renormalised: 0.70 / 0.70 → 1.0.
    assert score == pytest.approx(1.0, abs=1e-9)


def test_phase_k_preserves_wrong_issue_penalty() -> None:
    """
    Phase K leaves the wrong-issue penalty intact.

    When issue numbers diverge (5 vs 6), s_issue returns 0.0. With
    Phase K, the score is renormalised over contributing signals — but
    the wrong issue is still penalised (the signal contributes a 0.0
    in the weighted sum).
    """
    score = metadata_score(make_profile(issue_int=5), make_candidate(issue="6"))
    # All 5 signals contribute, s_issue=0.0, others=1.0.
    # weighted = 0.30 + 0 + 0.10 + 0.10 + 0.05 = 0.55; total_weight=0.80
    # score = 0.55/0.80 = 0.6875
    assert score == pytest.approx(0.6875, abs=1e-9)
