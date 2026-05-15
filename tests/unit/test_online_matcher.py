"""Online matcher tests: signals, scoring, policy resolution."""

from __future__ import annotations

import pytest

from comicbox.config.settings import OnlineSettings, Policy
from comicbox.online.matcher import (
    OnlineMatcher,
    ResolutionKind,
    metadata_score,
)
from comicbox.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
    parse_issue_int,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.online.signals import (
    s_issue,
    s_pages,
    s_publisher,
    s_series,
    s_year,
)


def _candidate(
    *,
    issue_id: int = 1,
    series: str = "Foo Comics",
    issue: str = "5",
    year: int | None = 2020,
    publisher: str | None = "Quality Comics",
    page_count: int | None = 24,
    volume_id: int | None = None,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series=series,
            issue=issue,
            year=year,
            publisher=publisher,
            page_count=page_count,
            cover_url=None,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


def _profile(**overrides) -> ComicProfile:
    base = {
        "series": "Foo Comics",
        "issue": "5",
        "issue_int": 5,
        "year": 2020,
        "publisher": "Quality Comics",
        "page_count": 24,
    }
    base.update(overrides)
    return ComicProfile(**base)


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
        assert s_series(_profile(), _candidate()) == 1.0

    def test_volume_suffix_normalized(self) -> None:
        score = s_series(
            _profile(series="Foo Comics"),
            _candidate(series="Foo Comics (Vol. 2)"),
        )
        assert score >= 0.8

    def test_punctuation_normalized(self) -> None:
        score = s_series(
            _profile(series="X-Men"),
            _candidate(series="X Men"),
        )
        assert score >= 0.8

    def test_missing_either_side_zero(self) -> None:
        assert s_series(_profile(series=None), _candidate()) == 0.0
        assert s_series(_profile(), _candidate(series="")) == 0.0


class TestIssueSignal:
    def test_int_match_is_one(self) -> None:
        assert s_issue(_profile(issue_int=5), _candidate(issue="5")) == 1.0
        assert s_issue(_profile(issue_int=5), _candidate(issue="005")) == 1.0

    def test_int_mismatch_is_zero(self) -> None:
        assert s_issue(_profile(issue_int=5), _candidate(issue="6")) == 0.0

    def test_string_match_is_one(self) -> None:
        assert (
            s_issue(_profile(issue_int=None, issue="1a"), _candidate(issue="1a")) == 1.0
        )

    def test_missing_one_side_returns_partial_credit(self) -> None:
        score = s_issue(_profile(issue=None, issue_int=None), _candidate(issue="5"))
        assert score == 0.5


class TestYearSignal:
    def test_exact_year_one(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2020)) == 1.0

    def test_off_by_one(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2021)) == 0.7

    def test_off_by_two(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2022)) == 0.4

    def test_off_by_three_decays_smoothly(self) -> None:
        """Phase F: diff=3 → 0.32 (was 0.0 under the original cliff)."""
        assert s_year(_profile(year=2020), _candidate(year=2023)) == pytest.approx(
            0.32, abs=1e-9
        )

    def test_off_by_four_continues_decay(self) -> None:
        """Phase F: linear decay from diff=2 to diff=7."""
        assert s_year(_profile(year=2020), _candidate(year=2024)) == pytest.approx(
            0.24, abs=1e-9
        )

    def test_off_by_six_near_cliff(self) -> None:
        """Phase F: diff=6 → 0.08, just before the cliff at diff=7."""
        assert s_year(_profile(year=2020), _candidate(year=2026)) == pytest.approx(
            0.08, abs=1e-9
        )

    def test_off_by_seven_hits_cliff(self) -> None:
        """Phase F: diff=7 still hits 0.0 — the long tail doesn't get year credit."""
        assert s_year(_profile(year=2020), _candidate(year=2027)) == 0.0

    def test_far_off_zero(self) -> None:
        assert s_year(_profile(year=2020), _candidate(year=2010)) == 0.0

    def test_both_missing_weak_prior(self) -> None:
        """Symmetric missing (no info on either side) → 0.5 prior."""
        assert s_year(_profile(year=None), _candidate(year=None)) == 0.5

    def test_asymmetric_missing_partial(self) -> None:
        """
        One side has year, the other doesn't → 0.3.

        Lower than any real-match bracket (even ±2 → 0.4) to avoid
        over-crediting wrong-volume candidates whose BasicIssue search
        result happens to lack a cover_date.
        """
        assert s_year(_profile(year=2020), _candidate(year=None)) == 0.3
        assert s_year(_profile(year=None), _candidate(year=2020)) == 0.3


class TestPublisherSignal:
    def test_exact(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="Quality Comics"),
                _candidate(publisher="Quality Comics"),
            )
            == 1.0
        )

    def test_normalized_match(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="Quality Comics, Inc."),
                _candidate(publisher="quality"),
            )
            == 1.0
        )

    def test_different(self) -> None:
        assert (
            s_publisher(
                _profile(publisher="DC"),
                _candidate(publisher="Marvel"),
            )
            == 0.0
        )

    def test_missing(self) -> None:
        assert s_publisher(_profile(publisher=None), _candidate()) == 0.5


class TestPagesSignal:
    def test_exact(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=24)) == 1.0

    def test_within_10pct(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=22)) == 0.7

    def test_within_25pct(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=20)) == 0.3

    def test_far_off(self) -> None:
        assert s_pages(_profile(page_count=24), _candidate(page_count=48)) == 0.0


# --------------------------------------------------------- scoring


def test_perfect_match_scores_one() -> None:
    score = metadata_score(_profile(), _candidate())
    assert score == pytest.approx(1.0)


def test_wrong_issue_drops_score() -> None:
    score = metadata_score(_profile(issue_int=5), _candidate(issue="6"))
    # Issue weight is 0.25 / 0.80 = ~0.3125; missing it should drop to ~0.6875.
    assert 0.65 < score < 0.72


def test_partial_match_above_min_confidence() -> None:
    # Right series + issue, missing publisher + pages, year off by one.
    score = metadata_score(
        _profile(publisher=None, page_count=None, year=2020),
        _candidate(publisher=None, page_count=None, year=2021),
    )
    assert score >= 0.50


# --------------------------------------------------------- resolution


def _settings(**overrides) -> OnlineSettings:
    return OnlineSettings(
        confidence_threshold=overrides.pop("confidence_threshold", 0.85),
        **overrides,
    )


# Default policy is `normal`, default unattended is False.
def test_auto_write_when_top_clears_threshold_with_gap() -> None:
    matcher = OnlineMatcher()
    ranked = [
        _candidate(issue_id=1),  # perfect match
        _candidate(issue_id=2, year=2010),  # far off year
    ]
    ranked = matcher.rank(_profile(), ranked)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_no_match_when_all_below_min_confidence() -> None:
    matcher = OnlineMatcher()
    # All candidates are wildly wrong.
    bad = [_candidate(series="Totally Different Series", issue="999", year=1900)]
    ranked = matcher.rank(_profile(), bad)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.NO_MATCH


def test_prompt_when_close_call_default_policy() -> None:
    matcher = OnlineMatcher()
    # Both candidates clear min_confidence with similar scores.
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),  # tiny ding
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_strict_unattended_skips_when_close() -> None:
    """`--unattended --policy strict` skips ambiguous → SKIP."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99, policy=Policy.STRICT, unattended=True),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.SKIP


def test_normal_accepts_solo_below_threshold() -> None:
    """`--policy normal` (default) takes a sole viable candidate even below auto-write bar."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1, page_count=22),  # 0.7 weight on pages
    ]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_strict_prompts_solo_below_threshold() -> None:
    """`--policy strict` requires unambig — solo viable below threshold prompts."""
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(_profile(), candidates)
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99, policy=Policy.STRICT),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.PROMPT


def test_eager_waives_gap_rule() -> None:
    """`--policy eager` auto-writes top above threshold even with narrow gap."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1),
        _candidate(issue_id=2, page_count=22),  # similar score
    ]
    ranked = matcher.rank(_profile(), candidates)
    # Pick a threshold that the top clears but the runner-up nearly does too.
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.50, policy=Policy.EAGER),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.AUTO_WRITE


def test_always_prompt_never_auto_writes() -> None:
    """`always-prompt` defers every viable case to the user."""
    matcher = OnlineMatcher()
    ranked = [
        _candidate(issue_id=1),  # perfect match
        _candidate(issue_id=2, year=2010),
    ]
    ranked = matcher.rank(_profile(), ranked)
    res = matcher.resolve(
        ranked, _settings(policy=Policy.ALWAYS_PROMPT), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_per_source_policy_override() -> None:
    """`policy_per_source['comicvine'] = strict` overrides the global policy."""
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(_profile(), candidates)
    settings = _settings(
        confidence_threshold=0.99,
        policy=Policy.NORMAL,
        policy_per_source={"comicvine": Policy.STRICT},
    )
    # Metron uses global = normal → AUTO_WRITE solo.
    res_metron = matcher.resolve(ranked, settings, source_name="metron")
    assert res_metron.kind is ResolutionKind.AUTO_WRITE
    # ComicVine uses override = strict → PROMPT.
    res_cv = matcher.resolve(ranked, settings, source_name="comicvine")
    assert res_cv.kind is ResolutionKind.PROMPT


def test_per_source_confidence_threshold_override() -> None:
    """`confidence_threshold_per_source` lets one source use a different bar."""
    matcher = OnlineMatcher()
    # Two candidates, both viable, top ~0.875 with small gap (year way off
    # docks ~0.125; page_count off docks a small extra). `eager` policy
    # depends only on threshold — neither solo_viable nor unambig fire here,
    # so the per-source threshold is the deciding knob.
    candidates = [
        _candidate(issue_id=1, year=2010),
        _candidate(issue_id=2, year=2010, page_count=22),
    ]
    ranked = matcher.rank(_profile(), candidates)
    settings = _settings(
        confidence_threshold=0.99,
        confidence_threshold_per_source={"metron": 0.50},
        policy=Policy.EAGER,
    )
    res_metron = matcher.resolve(ranked, settings, source_name="metron")
    assert res_metron.kind is ResolutionKind.AUTO_WRITE
    res_cv = matcher.resolve(ranked, settings, source_name="comicvine")
    assert res_cv.kind is ResolutionKind.PROMPT


# ----------------------------------------- score-tie tiebreak by volume_id


def test_rank_breaks_ties_by_lower_volume_id() -> None:
    """
    When two candidates score identically, the lower volume_id wins.

    Replicates the Watchmen (1987) #5 case: two CV issue records with
    bit-identical metadata land at the same blended score; the canonical
    volume (vol=3622) must beat the duplicate (vol=79545) regardless of
    the order the source returned them.
    """
    matcher = OnlineMatcher()
    # Source returns the dupe first — simulating CV's actual response order.
    candidates = [
        _candidate(issue_id=476696, volume_id=79545),  # dupe
        _candidate(issue_id=27650, volume_id=3622),  # canonical
    ]
    ranked = matcher.rank(_profile(), candidates)
    # Canonical wins despite arriving second.
    assert ranked[0].issue_id == 27650
    assert ranked[0].volume_id == 3622


def test_rank_within_volume_tiebreak_by_lower_issue_id() -> None:
    """Tied score AND tied volume_id (variant covers) → lower issue_id wins."""
    matcher = OnlineMatcher()
    # Both from the same volume — variant cover scenario.
    candidates = [
        _candidate(issue_id=500, volume_id=100),
        _candidate(issue_id=400, volume_id=100),  # canonical (lower)
    ]
    ranked = matcher.rank(_profile(), candidates)
    assert ranked[0].issue_id == 400


def test_rank_tiebreak_treats_none_volume_id_as_lowest_priority() -> None:
    """None volume_id sorts to the bottom of a tie (we trust known data)."""
    matcher = OnlineMatcher()
    candidates = [
        _candidate(issue_id=1, volume_id=None),
        _candidate(issue_id=2, volume_id=999),
    ]
    ranked = matcher.rank(_profile(), candidates)
    # Even though id=1 is lower, the known volume_id beats the unknown.
    assert ranked[0].issue_id == 2


def test_rank_score_dominates_over_volume_id_tiebreak() -> None:
    """A clearly higher score wins regardless of volume_id ordering."""
    matcher = OnlineMatcher()
    # Top scorer has a *higher* volume_id; should still win.
    candidates = [
        _candidate(issue_id=1, volume_id=1, year=2010),  # year off → lower md
        _candidate(issue_id=2, volume_id=9999),  # perfect match
    ]
    ranked = matcher.rank(_profile(), candidates)
    assert ranked[0].issue_id == 2
    # Score gap is non-trivial — not a tie.
    assert ranked[0].score > ranked[1].score


def test_candidate_sort_key_stable_ordering() -> None:
    """Direct test of the sort key for unit-level coverage."""
    from comicbox.online.matcher import _candidate_sort_key

    c1 = _candidate(issue_id=1, volume_id=100)
    c2 = _candidate(issue_id=2, volume_id=50)
    c3 = _candidate(issue_id=3, volume_id=None)
    # Force identical metadata_score / final score by direct construction.
    from dataclasses import replace

    c1 = replace(c1, metadata_score=0.9, score=0.9)
    c2 = replace(c2, metadata_score=0.9, score=0.9)
    c3 = replace(c3, metadata_score=0.9, score=0.9)
    keys = sorted([c1, c2, c3], key=_candidate_sort_key)
    # Lower volume_id wins; None sorts to bottom.
    assert [c.issue_id for c in keys] == [2, 1, 3]


# ----------------------------- tied-metadata near-blend-score tiebreak


def test_apply_tied_metadata_tiebreak_reorders_near_tied_same_md() -> None:
    """
    Reorder near-tied same-md candidates: canonical volume wins.

    Watchmen #009 shape: same md (0.91), small cover-hash difference
    moves blended scores by 0.01. Without this pass the dupe-volume
    candidate (higher cover hash but higher vol_id) wins; with it, the
    canonical volume wins.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    # The wrong volume's slight cover edge gives it a fractionally higher
    # blended score in the input order.
    wrong = _candidate(issue_id=476700, volume_id=79545)
    right = _candidate(issue_id=28090, volume_id=3622)
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.84, score=0.896)
    right = _replace(right, metadata_score=0.91, cover_score=0.81, score=0.890)

    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    # Canonical vol wins despite arriving with a 0.006 score deficit.
    assert ranked[0].issue_id == 28090
    assert ranked[0].volume_id == 3622


def test_apply_tied_metadata_tiebreak_respects_different_md() -> None:
    """
    Leave different-md candidates alone — cover does legitimate work there.

    Genuine cover-hash disambiguation case: different metadata scores,
    blended ties. The metadata-equality predicate is the safety rail.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    # A: md=0.85 (weaker), but covers very similar (cover=0.95) → blended 0.87.
    # B: md=0.95 (strong), but cover different (cover=0.55) → blended 0.87.
    # Different metadata; the post-pass should NOT collapse them.
    a = _candidate(issue_id=1, volume_id=999)
    b = _candidate(issue_id=2, volume_id=100)
    a = _replace(a, metadata_score=0.85, cover_score=0.95, score=0.87)
    b = _replace(b, metadata_score=0.95, cover_score=0.55, score=0.87)

    # Input order: A first (entered first). Different md → no re-ordering.
    ranked = _apply_tied_metadata_tiebreak([a, b])
    assert ranked == [a, b]


def test_apply_tied_metadata_tiebreak_score_gap_too_wide() -> None:
    """
    Leave alone when same md but blended score gap > the margin.

    Score gap > 0.02 means the matcher distinguished them clearly via
    the cover-hash signal — the volume_id correction shouldn't override.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    # md tied, but score gap of 0.05 (> the 0.02 margin)
    high = _candidate(issue_id=1, volume_id=999)
    low = _candidate(issue_id=2, volume_id=100)
    high = _replace(high, metadata_score=0.91, cover_score=0.95, score=0.94)
    low = _replace(low, metadata_score=0.91, cover_score=0.70, score=0.89)
    ranked = _apply_tied_metadata_tiebreak([high, low])
    # No swap — the gap is meaningful; the higher cover legitimately wins.
    assert ranked[0].issue_id == 1


def test_apply_tied_metadata_tiebreak_handles_empty_and_single() -> None:
    """Empty + single-element lists are no-ops."""
    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    assert _apply_tied_metadata_tiebreak([]) == []
    [c] = _apply_tied_metadata_tiebreak([_candidate()])
    assert c is not None


def test_rank_applies_tied_metadata_tiebreak_in_metadata_only_path() -> None:
    """End-to-end via OnlineMatcher.rank, no hashing path."""
    matcher = OnlineMatcher()
    # Two candidates where one's cover_score on construction is already
    # set — but the rank path won't invoke hashing (no provider). So
    # scores reflect metadata-only output. Use perfect-match candidates
    # to force md=1.0 on both, then perturb post-rank to test the
    # post-pass directly is enough — but to test the wired path we
    # rely on the perfect-match producing identical metadata + scores.
    candidates = [
        _candidate(issue_id=476700, volume_id=79545),  # dupe vol
        _candidate(issue_id=28090, volume_id=3622),  # canonical
    ]
    ranked = matcher.rank(_profile(), candidates)
    # Identical metadata → identical scores → vol_id tiebreak (via sort
    # key OR post-pass; both agree). Canonical wins.
    assert ranked[0].issue_id == 28090


def test_apply_tied_metadata_tiebreak_respects_cover_signal_when_diff_large() -> None:
    """
    When same-md but cover-score gap is real, keep the cover-winner.

    Original Sin (2014) #001 shape: two records, both at md=0.91. One has
    cover_score=1.00 (perfect Hamming match — the right answer); the
    other has cover_score=0.91 (close but not identical). The 0.09 gap
    is real signal, not hash noise. Without the cover-diff predicate
    the old tiebreak would group them and let vol_id win — which would
    pick the WRONG answer (the higher cover_score is the right one).
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    # Source returns near-tied candidates: vol=73241 first by API order,
    # vol=77906 second. After scoring, the perfect-cover one has higher
    # blended score (0.928 vs 0.910).
    wrong = _candidate(issue_id=452317, volume_id=73241)
    right = _candidate(issue_id=469279, volume_id=77906)
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.91, score=0.910)
    right = _replace(right, metadata_score=0.91, cover_score=1.00, score=0.928)

    # The input order is high-score-first after the upstream sort:
    ranked = _apply_tied_metadata_tiebreak([right, wrong])
    # The cover-diff predicate must REJECT the grouping (0.09 > 0.03),
    # leaving the cover-winner at rank 1 despite higher vol_id.
    assert ranked[0].issue_id == 469279
    assert ranked[0].cover_score == 1.00


def test_apply_tied_metadata_tiebreak_cover_diff_within_margin_is_noise() -> None:
    """
    Phase G: cover diff within the 0.03 noise margin is still noise.

    Watchmen #009 dupe shape: same md (0.91), cover-hash difference of
    ~0.025 (within 2 Hamming bits). The Phase G threshold (0.03) treats
    this as noise — tiebreak fires, canonical (lower vol_id) wins. This
    locks in the Phase G boundary: tightening to 0.02 would make this
    case a signal, which we don't want (covers are essentially
    identical — variant scan, slight Hamming jitter).
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=476700, volume_id=79545)
    right = _candidate(issue_id=28090, volume_id=3622)
    # Cover diff = 0.025 (unambiguously within 0.03 margin in float math).
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.85, score=0.915)
    right = _replace(right, metadata_score=0.91, cover_score=0.825, score=0.910)

    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    # 0.025 < 0.03 = noise → tiebreak fires → canonical (lower vol_id) wins.
    assert ranked[0].issue_id == 28090
    assert ranked[0].volume_id == 3622


def test_apply_tied_metadata_tiebreak_high_quality_small_diff_is_signal() -> None:
    """
    Phase I: at near-perfect cover scores, a small diff IS signal.

    Hawkeye Freefall (bigmedia 2026-05-14) shape: both candidates have
    cover_score ≥ 0.94 (near-perfect Hamming matches); diff is 0.03.
    Phase G's absolute 0.03 threshold collapsed this as noise (wrong).
    Phase I looks at room-to-perfect: 1 - 0.94 = 0.06, ratio = 0.03/0.06
    = 0.5 → at the relative threshold; cover-winner stays.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=10000, volume_id=100)  # lower vol_id
    right = _candidate(issue_id=10001, volume_id=200)  # higher vol_id
    # Cover diff = 0.03 at min=0.94 → ratio 0.5 → signal.
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.94, score=0.916)
    right = _replace(right, metadata_score=0.91, cover_score=0.97, score=0.922)

    ranked = _apply_tied_metadata_tiebreak([right, wrong])
    assert ranked[0].issue_id == 10001
    assert ranked[0].volume_id == 200


def test_apply_tied_metadata_tiebreak_medium_quality_small_diff_is_noise() -> None:
    """
    Phase I: at medium cover scores, a small diff is hash noise.

    Same Watchmen #009 dupe shape as `cover_diff_within_margin_is_noise`
    but anchored to the Phase I formula explicitly. Both candidates at
    cover_score 0.81 / 0.84 (medium quality matches); diff=0.03 is 16%
    of the room-to-perfect at min=0.81 → noise → vol_id wins.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=476700, volume_id=79545)
    right = _candidate(issue_id=28090, volume_id=3622)
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.84, score=0.916)
    right = _replace(right, metadata_score=0.91, cover_score=0.81, score=0.910)

    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    assert ranked[0].issue_id == 28090
    assert ranked[0].volume_id == 3622


def test_apply_tied_metadata_tiebreak_large_diff_always_signal() -> None:
    """
    Phase I: any diff ≥ 0.10 is signal regardless of score level.

    Hilda Stone Forest shape (bigmedia): cover_score 1.00 vs 0.59,
    diff=0.41. The absolute floor catches it — these are genuinely
    different covers, not hash noise.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=10000, volume_id=100)
    right = _candidate(issue_id=10001, volume_id=200)
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.59, score=0.850)
    right = _replace(right, metadata_score=0.91, cover_score=1.00, score=0.928)

    ranked = _apply_tied_metadata_tiebreak([right, wrong])
    assert ranked[0].issue_id == 10001


def test_apply_tied_metadata_tiebreak_both_perfect_is_noise() -> None:
    """
    Phase I: two candidates both at 1.00 are degenerate → noise.

    When min(a, b) == 1.0, room-to-perfect = 0 which would divide by
    zero. The implementation short-circuits to noise (vol_id wins),
    which is correct: two perfect-cover matches are interchangeable
    by the cover signal alone.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=10000, volume_id=200)  # higher vol_id
    right = _candidate(issue_id=10001, volume_id=100)  # lower vol_id (canonical)
    wrong = _replace(wrong, metadata_score=0.91, cover_score=1.00, score=0.928)
    right = _replace(right, metadata_score=0.91, cover_score=1.00, score=0.928)

    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    # Canonical (lower vol_id) wins via tiebreak.
    assert ranked[0].volume_id == 100


def test_apply_tied_metadata_tiebreak_skips_when_cover_score_missing() -> None:
    """
    Missing cover_score on either side → treat as noise, apply vol_id tiebreak.

    This is the metadata-only path: no hashing fired, both cover_scores
    are None. We have no cover information to make a decision, so fall
    back to the canonical-record preference.
    """
    from dataclasses import replace as _replace

    from comicbox.online.matcher import _apply_tied_metadata_tiebreak

    wrong = _candidate(issue_id=2, volume_id=999)
    right = _candidate(issue_id=1, volume_id=100)
    # Both at the same score, no cover hashing.
    wrong = _replace(wrong, metadata_score=0.91, cover_score=None, score=0.91)
    right = _replace(right, metadata_score=0.91, cover_score=None, score=0.91)
    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    # Lower vol_id wins — the cover signal is absent so it can't push
    # the decision away from the canonical-record preference.
    assert ranked[0].issue_id == 1


# ------------- Phase E: solo-viable confidence floor


def test_solo_viable_below_floor_prompts_under_normal() -> None:
    """
    A lone candidate below `solo_confidence_threshold` prompts under NORMAL.

    Reproduces the Groo and Wanted Dossier silent-failure pattern from the
    slimlib calibration: CV's search returned a single candidate scoring
    in the 0.85-0.95 range; the actual right answer wasn't in CV's top-5.
    Pre-Phase-E, NORMAL's `solo_viable` carve-out auto-wrote the wrong
    answer silently. Phase E gates that carve-out on the new floor.
    """
    matcher = OnlineMatcher()
    # Year off by 2 (0.4 weight) + pages within 25% (0.3 weight) →
    # raw = 0.30+0.25+0.10*0.4+0.10+0.05*0.3 = 0.705; normalized = 0.881.
    candidates = [_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(_profile(), candidates)
    # Sanity: score is in the auto-write band but below the 0.95 floor.
    assert 0.85 < ranked[0].score < 0.95
    # Use confidence_threshold=0.99 so `unambig` is False (top<threshold) —
    # forces the policy decision through the solo_viable carve-out path.
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99),
        source_name="metron",
    )
    # Pre-Phase-E this would have been AUTO_WRITE (solo_viable=True).
    # Phase E: solo confidence floor (0.95) is not cleared → PROMPT.
    assert res.kind is ResolutionKind.PROMPT


def test_solo_viable_above_floor_still_auto_writes_under_normal() -> None:
    """
    A solo candidate at or above the floor still auto-writes under NORMAL.

    Phase E doesn't trap high-confidence solo matches. A perfect-match
    candidate scores 1.0, which clears the default 0.95 floor. The
    carve-out still fires, just behind a stricter gate.
    """
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1)]  # perfect match → score = 1.0
    ranked = matcher.rank(_profile(), candidates)
    assert ranked[0].score == pytest.approx(1.0)
    # confidence_threshold=0.99: top=1.0 clears it, so unambig=True →
    # AUTO_WRITE without consulting solo_viable_confident. Either way
    # auto-writes: this confirms the floor isn't a trap for clean matches.
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.AUTO_WRITE


def test_solo_confidence_threshold_per_source_override_relaxes_floor() -> None:
    """
    Per-source override of `solo_confidence_threshold` restores permissiveness.

    Setting per-source to 0.50 (= min_confidence) re-enables the pre-
    Phase-E behavior: any solo candidate above min_confidence auto-writes
    under NORMAL.
    """
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(_profile(), candidates)
    assert 0.85 < ranked[0].score < 0.95

    settings_strict = _settings(confidence_threshold=0.99)
    settings_relaxed = _settings(
        confidence_threshold=0.99,
        solo_confidence_threshold_per_source={"metron": 0.50},
    )

    # Default floor (0.95): solo below → PROMPT.
    assert matcher.resolve(ranked, settings_strict, "metron").kind is (
        ResolutionKind.PROMPT
    )
    # Per-source floor (0.50): solo above min_confidence → AUTO_WRITE.
    assert matcher.resolve(ranked, settings_relaxed, "metron").kind is (
        ResolutionKind.AUTO_WRITE
    )


def test_solo_confidence_floor_does_not_affect_strict() -> None:
    """
    STRICT has no `solo_viable` carve-out so the floor is irrelevant.

    STRICT's auto-write rule is just `unambig` (top ≥ threshold AND gap
    ≥ margin). A solo candidate below threshold prompts regardless of
    the solo floor's value.
    """
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(_profile(), candidates)

    # Even with the floor relaxed to 0.50, STRICT still prompts —
    # because STRICT never consulted the solo carve-out anyway.
    settings_relaxed_strict = _settings(
        confidence_threshold=0.99,
        policy=Policy.STRICT,
        solo_confidence_threshold_per_source={"metron": 0.50},
    )
    res = matcher.resolve(ranked, settings_relaxed_strict, "metron")
    assert res.kind is ResolutionKind.PROMPT


def test_solo_confidence_floor_gates_eager_solo_carve_out() -> None:
    """
    EAGER's `solo_viable` path is gated by the same floor as NORMAL's.

    Pre-Phase-E EAGER auto-wrote any solo candidate above min_confidence
    regardless of how close to the confidence threshold it scored.
    Phase E gates that on the solo floor too — defense-in-depth for
    EAGER users who didn't intend "auto-write 0.50-scored solo matches."
    """
    matcher = OnlineMatcher()
    candidates = [_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(_profile(), candidates)
    settings_eager = _settings(
        policy=Policy.EAGER,
        confidence_threshold=0.99,  # so top_score>=threshold isn't met
    )
    # 0.88 < 0.95 floor AND 0.88 < 0.99 confidence_threshold → PROMPT.
    res = matcher.resolve(ranked, settings_eager, "metron")
    assert res.kind is ResolutionKind.PROMPT


# ------------- Phase J: adaptive top-K for cover hashing


class TestTopKForHashing:
    """Adaptive cover-hash K scales with candidate count."""

    def test_small_set_uses_minimum(self) -> None:
        """≤10 candidates → K stays at the original 5 (no behavior change)."""
        from comicbox.online.matcher import (
            _TOP_K_FOR_HASHING_MIN,
            _top_k_for_hashing,
        )

        assert _top_k_for_hashing(1) == _TOP_K_FOR_HASHING_MIN
        assert _top_k_for_hashing(5) == _TOP_K_FOR_HASHING_MIN
        assert _top_k_for_hashing(10) == _TOP_K_FOR_HASHING_MIN

    def test_medium_set_scales_up(self) -> None:
        """11-29 candidates → K = candidate_count // 2 (linear scale)."""
        from comicbox.online.matcher import _top_k_for_hashing

        # Boundary: 12 → 6 (linear).
        assert _top_k_for_hashing(12) == 6
        # Mid-range: 20 → 10.
        assert _top_k_for_hashing(20) == 10
        # Just under cap: 28 → 14.
        assert _top_k_for_hashing(28) == 14

    def test_large_set_caps_at_max(self) -> None:
        """≥30 candidates → K caps at the 15 budget bound."""
        from comicbox.online.matcher import (
            _TOP_K_FOR_HASHING_MAX,
            _top_k_for_hashing,
        )

        assert _top_k_for_hashing(30) == _TOP_K_FOR_HASHING_MAX
        assert _top_k_for_hashing(100) == _TOP_K_FOR_HASHING_MAX
        assert _top_k_for_hashing(1000) == _TOP_K_FOR_HASHING_MAX

    def test_apply_cover_hashing_hashes_more_when_set_is_large(self) -> None:
        """
        End-to-end: large candidate sets get more hashes than top-5.

        Lays out 12 candidates so the adaptive K kicks in (12 // 2 = 6).
        Counts cover_score!=None on the result — that count IS the
        number of candidates that got hashed.
        """
        from dataclasses import replace as _replace

        from comicbox.online.matcher import _apply_cover_hashing

        hashes: dict[str, str] = {
            "http://example.com/c1.jpg": "ffffffffffffffff",
        }

        def fake_fetcher(url: str) -> str:
            return hashes.get(url, "ffffffffffffffff")

        # 12 candidates, all with the same cover URL so they all get
        # a valid cover_score post-hashing.
        candidates = []
        for i in range(12):
            c = _candidate(issue_id=i)
            c = _replace(c, metadata_score=0.9 - 0.01 * i, score=0.9 - 0.01 * i)
            c = _replace(
                c,
                summary=_replace(c.summary, cover_url="http://example.com/c1.jpg"),
            )
            candidates.append(c)

        result = _apply_cover_hashing(
            candidates,
            local_hash="0000000000000000",
            candidate_hash_fetcher=fake_fetcher,
        )

        # Adaptive K = 12 // 2 = 6. So 6 candidates got hashed.
        hashed = sum(1 for c in result if c.cover_score is not None)
        assert hashed == 6
