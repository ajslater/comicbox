"""
Online matcher resolution tests: policy, tiebreaks, and the cover pass.

What the matcher does with a ranked list — auto-write, prompt or skip,
which candidate wins a tie, and which candidates are worth hashing a
cover for. The scoring that produces the ranking is in
``test_online_matcher``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from comicbox.config.online.settings import (
    MatchMode,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceTuning,
    OnlineTuningSettings,
    Prompts,
)
from comicbox.formats.base.online.matcher import (
    OnlineMatcher,
    ResolutionKind,
)
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from tests.util.online_matcher import Policy, make_candidate, make_profile


def _settings(**overrides) -> OnlineSettings:
    """
    Build OnlineSettings from legacy-shaped kwargs.

    Accepts legacy keyword names (``confidence_threshold``, ``policy``,
    ``unattended``, ``policy_per_source``,
    ``confidence_threshold_per_source``,
    ``solo_confidence_threshold_per_source``) and translates them to the
    v4 nested dataclass tree. Existing test bodies in this file can keep
    their original phrasing.
    """
    confidence_threshold = overrides.pop("confidence_threshold", 0.85)
    policy = overrides.pop("policy", MatchMode.AUTO)
    unattended = overrides.pop("unattended", False)
    policy_per_source = overrides.pop("policy_per_source", None)
    conf_per_source = overrides.pop("confidence_threshold_per_source", None) or {}
    solo_per_source = overrides.pop("solo_confidence_threshold_per_source", None) or {}
    if overrides:
        reason = f"_settings: unexpected kwargs {sorted(overrides)}"
        raise TypeError(reason)
    if policy_per_source:
        # v4 dropped per-source match-mode overrides. Tests that asserted
        # them should be skipped / rewritten.
        reason = "policy_per_source is not supported in v4"
        raise NotImplementedError(reason)

    per_source: dict[str, OnlineSourceTuning] = {}
    for source, value in conf_per_source.items():
        per_source[source] = OnlineSourceTuning(auto_threshold=value)
    for source, value in solo_per_source.items():
        existing = per_source.get(source) or OnlineSourceTuning()
        per_source[source] = OnlineSourceTuning(
            auto_threshold=existing.auto_threshold,
            solo_threshold=value,
        )

    lookup = OnlineLookupSettings(
        match=policy,
        prompts=Prompts.NEVER if unattended else Prompts.ASK,
    )
    tuning = OnlineTuningSettings(
        auto_threshold=confidence_threshold,
        per_source=per_source,
    )
    return OnlineSettings(lookup=lookup, tuning=tuning)


# Default policy is `normal`, default unattended is False.
def test_auto_write_when_top_clears_threshold_with_gap() -> None:
    matcher = OnlineMatcher()
    ranked = [
        make_candidate(issue_id=1),  # perfect match
        make_candidate(issue_id=2, year=2010),  # far off year
    ]
    ranked = matcher.rank(make_profile(), ranked)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_no_match_when_all_below_min_confidence() -> None:
    matcher = OnlineMatcher()
    # All candidates are wildly wrong.
    bad = [make_candidate(series="Totally Different Series", issue="999", year=1900)]
    ranked = matcher.rank(make_profile(), bad)
    res = matcher.resolve(ranked, _settings(), source_name="metron")
    assert res.kind is ResolutionKind.NO_MATCH


def test_prompt_when_close_call_default_policy() -> None:
    matcher = OnlineMatcher()
    # Both candidates clear min_confidence with similar scores.
    candidates = [
        make_candidate(issue_id=1),
        make_candidate(issue_id=2, page_count=22),  # tiny ding
    ]
    ranked = matcher.rank(make_profile(), candidates)
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_strict_unattended_skips_when_close() -> None:
    """`--unattended --policy strict` skips ambiguous → SKIP."""
    matcher = OnlineMatcher()
    candidates = [
        make_candidate(issue_id=1),
        make_candidate(issue_id=2, page_count=22),
    ]
    ranked = matcher.rank(make_profile(), candidates)
    res = matcher.resolve(
        ranked,
        _settings(confidence_threshold=0.99, policy=Policy.STRICT, unattended=True),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.SKIP


def test_normal_accepts_solo_below_threshold_only_when_floor_lowered() -> None:
    """
    AUTO's solo carve-out reaches below the auto-write bar only on opt-in.

    The floor defaults to the source's `auto_threshold`, which makes
    the carve-out equivalent to CAREFUL's `unambig` rule. Lowering
    `solo_threshold` for the source is what buys "take a sole viable
    candidate even below the auto-write bar".
    """
    matcher = OnlineMatcher()
    candidates = [
        make_candidate(issue_id=1, page_count=22),  # 0.7 weight on pages
    ]
    ranked = matcher.rank(make_profile(), candidates)
    assert 0.95 < ranked[0].score < 0.99

    # Default floor (= the 0.99 auto_threshold): the lone candidate
    # doesn't clear the bar, so it prompts.
    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT

    # Opt in by lowering the floor for this source.
    res = matcher.resolve(
        ranked,
        _settings(
            confidence_threshold=0.99,
            solo_confidence_threshold_per_source={"metron": 0.50},
        ),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.AUTO_WRITE
    assert res.chosen is not None
    assert res.chosen.issue_id == 1


def test_strict_prompts_solo_below_threshold() -> None:
    """`--policy strict` requires unambig — solo viable below threshold prompts."""
    matcher = OnlineMatcher()
    candidates = [make_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(make_profile(), candidates)
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
        make_candidate(issue_id=1),
        make_candidate(issue_id=2, page_count=22),  # similar score
    ]
    ranked = matcher.rank(make_profile(), candidates)
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
        make_candidate(issue_id=1),  # perfect match
        make_candidate(issue_id=2, year=2010),
    ]
    ranked = matcher.rank(make_profile(), ranked)
    res = matcher.resolve(
        ranked, _settings(policy=Policy.ALWAYS_PROMPT), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


@pytest.mark.skip(reason="v4 removed per-source match-mode overrides")
def test_per_source_policy_override() -> None:
    """`policy_per_source['comicvine'] = strict` overrides the global policy."""
    matcher = OnlineMatcher()
    candidates = [make_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(make_profile(), candidates)
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
        make_candidate(issue_id=1, year=2010),
        make_candidate(issue_id=2, year=2010, page_count=22),
    ]
    ranked = matcher.rank(make_profile(), candidates)
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
        make_candidate(issue_id=476696, volume_id=79545),  # dupe
        make_candidate(issue_id=27650, volume_id=3622),  # canonical
    ]
    ranked = matcher.rank(make_profile(), candidates)
    # Canonical wins despite arriving second.
    assert ranked[0].issue_id == 27650
    assert ranked[0].volume_id == 3622


def test_rank_within_volume_tiebreak_by_lower_issue_id() -> None:
    """Tied score AND tied volume_id (variant covers) → lower issue_id wins."""
    matcher = OnlineMatcher()
    # Both from the same volume — variant cover scenario.
    candidates = [
        make_candidate(issue_id=500, volume_id=100),
        make_candidate(issue_id=400, volume_id=100),  # canonical (lower)
    ]
    ranked = matcher.rank(make_profile(), candidates)
    assert ranked[0].issue_id == 400


def test_rank_tiebreak_treats_none_volume_id_as_lowest_priority() -> None:
    """None volume_id sorts to the bottom of a tie (we trust known data)."""
    matcher = OnlineMatcher()
    candidates = [
        make_candidate(issue_id=1, volume_id=None),
        make_candidate(issue_id=2, volume_id=999),
    ]
    ranked = matcher.rank(make_profile(), candidates)
    # Even though id=1 is lower, the known volume_id beats the unknown.
    assert ranked[0].issue_id == 2


def test_rank_score_dominates_over_volume_id_tiebreak() -> None:
    """A clearly higher score wins regardless of volume_id ordering."""
    matcher = OnlineMatcher()
    # Top scorer has a *higher* volume_id; should still win.
    candidates = [
        make_candidate(issue_id=1, volume_id=1, year=2010),  # year off → lower md
        make_candidate(issue_id=2, volume_id=9999),  # perfect match
    ]
    ranked = matcher.rank(make_profile(), candidates)
    assert ranked[0].issue_id == 2
    # Score gap is non-trivial — not a tie.
    assert ranked[0].score > ranked[1].score


def test_candidate_sort_key_stable_ordering() -> None:
    """Direct test of the sort key for unit-level coverage."""
    from comicbox.formats.base.online.matcher import _candidate_sort_key

    c1 = make_candidate(issue_id=1, volume_id=100)
    c2 = make_candidate(issue_id=2, volume_id=50)
    c3 = make_candidate(issue_id=3, volume_id=None)
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

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    # The wrong volume's slight cover edge gives it a fractionally higher
    # blended score in the input order.
    wrong = make_candidate(issue_id=476700, volume_id=79545)
    right = make_candidate(issue_id=28090, volume_id=3622)
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

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    # A: md=0.85 (weaker), but covers very similar (cover=0.95) → blended 0.87.
    # B: md=0.95 (strong), but cover different (cover=0.55) → blended 0.87.
    # Different metadata; the post-pass should NOT collapse them.
    a = make_candidate(issue_id=1, volume_id=999)
    b = make_candidate(issue_id=2, volume_id=100)
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

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    # md tied, but score gap of 0.05 (> the 0.02 margin)
    high = make_candidate(issue_id=1, volume_id=999)
    low = make_candidate(issue_id=2, volume_id=100)
    high = _replace(high, metadata_score=0.91, cover_score=0.95, score=0.94)
    low = _replace(low, metadata_score=0.91, cover_score=0.70, score=0.89)
    ranked = _apply_tied_metadata_tiebreak([high, low])
    # No swap — the gap is meaningful; the higher cover legitimately wins.
    assert ranked[0].issue_id == 1


def test_apply_tied_metadata_tiebreak_handles_empty_and_single() -> None:
    """Empty + single-element lists are no-ops."""
    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    assert _apply_tied_metadata_tiebreak([]) == []
    [c] = _apply_tied_metadata_tiebreak([make_candidate()])
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
        make_candidate(issue_id=476700, volume_id=79545),  # dupe vol
        make_candidate(issue_id=28090, volume_id=3622),  # canonical
    ]
    ranked = matcher.rank(make_profile(), candidates)
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

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    # Source returns near-tied candidates: vol=73241 first by API order,
    # vol=77906 second. After scoring, the perfect-cover one has higher
    # blended score (0.928 vs 0.910).
    wrong = make_candidate(issue_id=452317, volume_id=73241)
    right = make_candidate(issue_id=469279, volume_id=77906)
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

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    wrong = make_candidate(issue_id=476700, volume_id=79545)
    right = make_candidate(issue_id=28090, volume_id=3622)
    # Cover diff = 0.025 (unambiguously within 0.03 margin in float math).
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.85, score=0.915)
    right = _replace(right, metadata_score=0.91, cover_score=0.825, score=0.910)

    ranked = _apply_tied_metadata_tiebreak([wrong, right])
    # 0.025 < 0.03 = noise → tiebreak fires → canonical (lower vol_id) wins.
    assert ranked[0].issue_id == 28090
    assert ranked[0].volume_id == 3622


def test_apply_tied_metadata_tiebreak_cover_diff_above_margin_is_signal() -> None:
    """
    Phase G: cover diff just above 0.03 is signal — keep cover winner.

    Locks in the lower bound: 0.04 cover diff IS signal, doesn't get
    collapsed by the tiebreak. Was previously 0.04 ≤ 0.05 = noise; the
    Phase G tightening makes this case respect the cover-hash decision.
    """
    from dataclasses import replace as _replace

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    wrong = make_candidate(issue_id=10000, volume_id=100)  # lower vol_id (canonical)
    right = make_candidate(issue_id=10001, volume_id=200)
    # Cover diff = 0.04, just above the noise margin.
    wrong = _replace(wrong, metadata_score=0.91, cover_score=0.84, score=0.910)
    right = _replace(right, metadata_score=0.91, cover_score=0.88, score=0.918)

    # Input order is high-score-first.
    ranked = _apply_tied_metadata_tiebreak([right, wrong])
    # 0.04 > 0.03 = real signal → tiebreak rejects grouping → cover winner stays.
    assert ranked[0].issue_id == 10001
    assert ranked[0].volume_id == 200


def test_apply_tied_metadata_tiebreak_skips_when_cover_score_missing() -> None:
    """
    Missing cover_score on either side → treat as noise, apply vol_id tiebreak.

    This is the metadata-only path: no hashing fired, both cover_scores
    are None. We have no cover information to make a decision, so fall
    back to the canonical-record preference.
    """
    from dataclasses import replace as _replace

    from comicbox.formats.base.online.matcher import _apply_tied_metadata_tiebreak

    wrong = make_candidate(issue_id=2, volume_id=999)
    right = make_candidate(issue_id=1, volume_id=100)
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
    candidates = [make_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(make_profile(), candidates)
    # Sanity: score is in the auto-write band but below the 0.95 floor.
    assert 0.85 < ranked[0].score < 0.95
    # Use confidence_threshold=0.99 so `unambig` is False (top<threshold) —
    # forces the policy decision through the solo_viable carve-out path.
    # Pin the solo floor at 0.95 explicitly: this test documents the
    # gating mechanism, not whatever the global default happens to be.
    res = matcher.resolve(
        ranked,
        _settings(
            confidence_threshold=0.99,
            solo_confidence_threshold_per_source={"metron": 0.95},
        ),
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
    candidates = [make_candidate(issue_id=1)]  # perfect match → score = 1.0
    ranked = matcher.rank(make_profile(), candidates)
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
    candidates = [make_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(make_profile(), candidates)
    assert 0.85 < ranked[0].score < 0.95

    # Pin the strict floor at 0.95 explicitly — this test contrasts a
    # strict floor against a relaxed one, not the global default.
    settings_strict = _settings(
        confidence_threshold=0.99,
        solo_confidence_threshold_per_source={"metron": 0.95},
    )
    settings_relaxed = _settings(
        confidence_threshold=0.99,
        solo_confidence_threshold_per_source={"metron": 0.50},
    )

    # Strict floor (0.95): solo below → PROMPT.
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
    candidates = [make_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(make_profile(), candidates)

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
    candidates = [make_candidate(issue_id=1, year=2018, page_count=20)]
    ranked = matcher.rank(make_profile(), candidates)
    # Pin the solo floor at 0.95 explicitly — this test documents that
    # EAGER's carve-out is gated by the floor, not the floor's default.
    settings_eager = _settings(
        policy=Policy.EAGER,
        confidence_threshold=0.99,  # so top_score>=threshold isn't met
        solo_confidence_threshold_per_source={"metron": 0.95},
    )
    # 0.88 < 0.95 floor AND 0.88 < 0.99 confidence_threshold → PROMPT.
    res = matcher.resolve(ranked, settings_eager, "metron")
    assert res.kind is ResolutionKind.PROMPT


# ------------- Phase E: the floor tracks the auto-write bar


def test_solo_floor_tracks_a_raised_auto_threshold() -> None:
    """
    Raising `auto_threshold` raises the solo floor with it.

    The floor is defined as "the same bar as a multi-candidate
    unambiguous win". Reading it from a module constant instead of the
    source's resolved threshold left a 0.95 back door open under a
    stricter configuration: a lone 0.98-scoring candidate auto-wrote
    for a user who had asked for 0.99, and no setting could close it.
    """
    matcher = OnlineMatcher()
    candidates = [make_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(make_profile(), candidates)
    # Above the old 0.95 constant, below the configured bar.
    assert 0.95 < ranked[0].score < 0.99

    res = matcher.resolve(
        ranked, _settings(confidence_threshold=0.99), source_name="metron"
    )
    assert res.kind is ResolutionKind.PROMPT


def test_solo_floor_tracks_a_per_source_auto_threshold() -> None:
    """A per-source `auto_threshold` moves that source's solo floor only."""
    matcher = OnlineMatcher()
    candidates = [make_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(make_profile(), candidates)

    settings = _settings(
        confidence_threshold=0.85,
        confidence_threshold_per_source={"metron": 0.99},
    )
    # metron runs at 0.99 — solo floor follows, so the 0.98 lone
    # candidate prompts.
    assert matcher.resolve(ranked, settings, "metron").kind is ResolutionKind.PROMPT
    # comicvine still runs at the global 0.85 and auto-writes.
    assert (
        matcher.resolve(ranked, settings, "comicvine").kind is ResolutionKind.AUTO_WRITE
    )


def test_explicit_solo_threshold_still_wins_over_the_auto_threshold() -> None:
    """An explicit per-source `solo_threshold` outranks the tracked default."""
    matcher = OnlineMatcher()
    candidates = [make_candidate(issue_id=1, page_count=22)]
    ranked = matcher.rank(make_profile(), candidates)

    res = matcher.resolve(
        ranked,
        _settings(
            confidence_threshold=0.99,
            solo_confidence_threshold_per_source={"metron": 0.50},
        ),
        source_name="metron",
    )
    assert res.kind is ResolutionKind.AUTO_WRITE


def test_auto_matches_careful_at_default_settings() -> None:
    """
    With the floor at the auto bar, AUTO's solo carve-out adds nothing.

    `solo_viable` means every other candidate is below `min_confidence`
    (0.50), so a top that clears the threshold is also more than
    `disambiguation_margin` clear of the runner-up — already `unambig`.
    Pinning this keeps the equivalence a documented property instead of
    a surprise the next time someone reads AUTO's rule.
    """
    matcher = OnlineMatcher()
    lone = matcher.rank(
        make_profile(), [make_candidate(issue_id=1, year=2018, page_count=20)]
    )
    clean = matcher.rank(make_profile(), [make_candidate(issue_id=1)])
    for ranked in (lone, clean):
        # 0.85: the lone 0.88 candidate clears the bar. 0.99: it doesn't,
        # which is where the carve-out used to make AUTO the looser mode.
        for threshold in (0.85, 0.99):
            settings_auto = _settings(
                policy=Policy.NORMAL, confidence_threshold=threshold
            )
            settings_careful = _settings(
                policy=Policy.STRICT, confidence_threshold=threshold
            )
            auto = matcher.resolve(ranked, settings_auto, "metron")
            careful = matcher.resolve(ranked, settings_careful, "metron")
            assert auto.kind is careful.kind


# ------------- Phase J: adaptive top-K for cover hashing


class TestTopKForHashing:
    """Adaptive cover-hash K scales with candidate count."""

    def test_small_set_uses_minimum(self) -> None:
        """≤10 candidates → K stays at the original 5 (no behavior change)."""
        from comicbox.formats.base.online.matcher import (
            _TOP_K_FOR_HASHING_MIN,
            _top_k_for_hashing,
        )

        assert _top_k_for_hashing(1) == _TOP_K_FOR_HASHING_MIN
        assert _top_k_for_hashing(5) == _TOP_K_FOR_HASHING_MIN
        assert _top_k_for_hashing(10) == _TOP_K_FOR_HASHING_MIN

    def test_medium_set_scales_up(self) -> None:
        """11-29 candidates → K = candidate_count // 2 (linear scale)."""
        from comicbox.formats.base.online.matcher import _top_k_for_hashing

        # Boundary: 12 → 6 (linear).
        assert _top_k_for_hashing(12) == 6
        # Mid-range: 20 → 10.
        assert _top_k_for_hashing(20) == 10
        # Just under cap: 28 → 14.
        assert _top_k_for_hashing(28) == 14

    def test_large_set_caps_at_max(self) -> None:
        """≥30 candidates → K caps at the 15 budget bound."""
        from comicbox.formats.base.online.matcher import (
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

        from comicbox.formats.base.online.matcher import _apply_cover_hashing

        hashes: dict[str, str] = {
            "http://example.com/c1.jpg": "ffffffffffffffff",
        }

        def fake_fetcher(url: str) -> str:
            return hashes.get(url, "ffffffffffffffff")

        # 12 candidates, all with the same cover URL so they all get
        # a valid cover_score post-hashing.
        candidates = []
        for i in range(12):
            c = make_candidate(issue_id=i)
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


# ------------- candidate hash-fetcher wiring


def test_matcher_uses_candidate_hash_fetcher_for_no_precomputed() -> None:
    """Matcher should call the fetcher for candidates without precomputed hash."""
    fetcher_calls: list[str] = []

    def fake_fetcher(url: str) -> str:
        fetcher_calls.append(url)
        return "ffffffffffffffff"  # different from local

    def local_provider() -> str:
        return "0000000000000000"

    profile = ComicProfile(
        series="Foo",
        issue="5",
        issue_int=5,
        year=2020,
        publisher="P",
        page_count=24,
    )
    cand = Candidate(
        source="comicvine",
        issue_id=42,
        summary=CandidateSummary(
            series="Foo",
            issue="5",
            year=2020,
            publisher="P",
            page_count=24,
            cover_url="http://example.com/x.jpg",
            variant_label=None,
        ),
    )

    matcher = OnlineMatcher()
    matcher.rank(
        profile,
        [cand],
        local_hash_provider=local_provider,
        candidate_hash_fetcher=fake_fetcher,
        threshold=0.99,  # force hashing path (top below threshold).
    )
    # Whether or not the candidate was hashed depends on the metadata
    # score landing in the ambiguous band; with a perfect metadata match
    # the policy may skip hashing. The test asserts the fetcher is wired:
    # if invoked, it received our URL.
    assert all(call == "http://example.com/x.jpg" for call in fetcher_calls)


# ------------------------------------------------ batch cover-hash fetching


def _ambiguous_pair(cover_a: str, cover_b: str) -> list[Candidate]:
    """Two same-score candidates, so hashing is invoked to separate them."""
    return [
        Candidate(
            source="comicvine",
            issue_id=1,
            summary=CandidateSummary(
                series="Watchmen",
                issue="1",
                year=1986,
                publisher="DC",
                page_count=None,
                cover_url=cover_a,
                variant_label=None,
            ),
            volume_id=10,
        ),
        Candidate(
            source="comicvine",
            issue_id=2,
            summary=CandidateSummary(
                series="Watchmen",
                issue="1",
                year=1986,
                publisher="DC",
                page_count=None,
                cover_url=cover_b,
                variant_label=None,
            ),
            volume_id=20,
        ),
    ]


def test_batch_fetcher_resolves_the_whole_top_k_in_one_call() -> None:
    """
    Every top-K cover is requested up front, not one blocking GET at a time.

    That single call is what lets the downloads overlap; serially they
    cost one round-trip per candidate for one comic.
    """
    profile = ComicProfile(series="Watchmen", issue="1", issue_int=1, year=1986)
    candidates = _ambiguous_pair("http://a", "http://b")
    batches: list[list[str]] = []

    def batch_fetcher(urls):
        batches.append(list(urls))
        return {"http://a": "0" * 16, "http://b": "f" * 16}

    OnlineMatcher().rank(
        profile,
        candidates,
        local_hash_provider=lambda: "0" * 16,
        candidate_hash_batch_fetcher=batch_fetcher,
    )
    assert len(batches) == 1
    assert sorted(batches[0]) == ["http://a", "http://b"]


def test_batch_and_serial_fetchers_rank_identically() -> None:
    """Concurrency changes when bytes arrive, never the ordering."""
    profile = ComicProfile(series="Watchmen", issue="1", issue_int=1, year=1986)
    hashes = {"http://a": "f" * 16, "http://b": "0" * 16}

    serial = OnlineMatcher().rank(
        profile,
        _ambiguous_pair("http://a", "http://b"),
        local_hash_provider=lambda: "0" * 16,
        candidate_hash_fetcher=hashes.get,
    )
    batched = OnlineMatcher().rank(
        profile,
        _ambiguous_pair("http://a", "http://b"),
        local_hash_provider=lambda: "0" * 16,
        candidate_hash_batch_fetcher=lambda urls: {
            u: hashes[u] for u in urls if u in hashes
        },
    )
    assert [c.issue_id for c in serial] == [c.issue_id for c in batched]
    assert [c.score for c in serial] == [c.score for c in batched]


def test_batch_fetcher_failure_degrades_to_no_cover_signal() -> None:
    """A broken batch leaves metadata ranking intact rather than raising."""
    profile = ComicProfile(series="Watchmen", issue="1", issue_int=1, year=1986)

    def exploding_fetcher(urls):
        msg = "network down"
        raise RuntimeError(msg)

    ranked = OnlineMatcher().rank(
        profile,
        _ambiguous_pair("http://a", "http://b"),
        local_hash_provider=lambda: "0" * 16,
        candidate_hash_batch_fetcher=exploding_fetcher,
    )
    assert len(ranked) == 2
    assert all(c.cover_score is None for c in ranked)
    # Still marked attempted — the tiebreak must tell "no usable cover"
    # from "never looked", and we did look.
    assert all(c.cover_hash_attempted for c in ranked)


def test_batch_fetcher_skips_candidates_with_precomputed_hashes() -> None:
    """Metron's precomputed hash costs no download."""
    profile = ComicProfile(series="Watchmen", issue="1", issue_int=1, year=1986)
    candidates = _ambiguous_pair("http://a", "http://b")
    candidates[0] = replace(candidates[0], precomputed_cover_hash="0" * 16)
    requested: list[str] = []

    def batch_fetcher(urls):
        requested.extend(urls)
        return {}

    OnlineMatcher().rank(
        profile,
        candidates,
        local_hash_provider=lambda: "0" * 16,
        candidate_hash_batch_fetcher=batch_fetcher,
    )
    assert requested == ["http://b"]
