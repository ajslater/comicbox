"""
Confidence-score matcher and policy resolution.

For M3 the matcher is metadata-only — cover hashing lives behind a
hook that returns `None` until M4 wires up `imagehash`.

Public surface:

- ``OnlineMatcher.rank`` — score and sort candidates against a profile.
- ``OnlineMatcher.resolve`` — apply the Match Resolution Policy
  (auto-write / prompt / skip / no-match).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Final

from loguru import logger

from comicbox.config.settings import (
    Policy,
    resolve_confidence_threshold,
    resolve_disambiguation_margin,
    resolve_min_confidence,
    resolve_policy,
    resolve_solo_confidence_threshold,
)
from comicbox.online.cover_hash import cover_score as _cover_score
from comicbox.online.signals import (
    s_issue,
    s_pages,
    s_publisher,
    s_series,
    s_year,
)

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings
    from comicbox.online.profile import Candidate, ComicProfile


# Callable that returns the local comic's pHash hex (or None if unavailable).
LocalHashProvider = Callable[[], str | None]

# Callable that fetches and hashes a candidate cover URL, with caching.
# Returns the hex hash string or None if unavailable.
CandidateHashFetcher = Callable[[str], str | None]


# Metadata-signal weights. Sum to 0.80; the remaining 0.20 is reserved
# for the cover-hash signal (M4). When hashing isn't invoked we
# renormalise to [0, 1] by dividing by the metadata weight sum.
W_SERIES = 0.30
W_ISSUE = 0.25
W_YEAR = 0.10
W_PUBLISHER = 0.10
W_PAGES = 0.05
_METADATA_WEIGHT_SUM = W_SERIES + W_ISSUE + W_YEAR + W_PUBLISHER + W_PAGES  # 0.80
W_COVER = 0.20

# Default constant kept here for the rank() default-arg signature; the
# matcher reads per-source values via `resolve_*` helpers in `_resolve_policy`
# and `_should_invoke_hashing` so per-source overrides take effect.
_DEFAULT_CONFIDENCE_THRESHOLD = 0.95


class ResolutionKind(str, Enum):
    """Outcome of applying the Match Resolution Policy."""

    AUTO_WRITE = "AUTO_WRITE"
    PROMPT = "PROMPT"
    SKIP = "SKIP"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True, slots=True)
class Resolution:
    """Matcher's final verdict for one (comic, source) pair."""

    kind: ResolutionKind
    chosen: Candidate | None
    candidates: tuple[Candidate, ...]


def metadata_score(profile: ComicProfile, candidate: Candidate) -> float:
    """
    Renormalised weighted sum of metadata signals, in [0, 1].

    Phase K (2026-05-14): only signals where BOTH sides have data
    contribute to the weighted sum, and the total is renormalised over
    the *contributing* weights — not the full `_METADATA_WEIGHT_SUM`.

    Why: ComicVine's `BasicIssue` (what `search` returns) doesn't expose
    publisher or page_count. Under the original formula, those signals
    returned weak-prior values (0.5/0.6) that diluted the score even
    when series/issue/year all matched perfectly. The structural cap
    for a CV BasicIssue candidate was md=0.91 — below the default
    confidence_threshold of 0.95 — so the matcher would PROMPT for
    obvious matches like "Wolverine #20 (2026)" → CV's "Wolverine #20
    (2026)" candidate.

    Phase K skips signals when either side is missing data. The
    Wolverine case scores series=1.0, issue=1.0, year=1.0, with
    publisher and pages both skipped (profile or candidate is None).
    Renormalised: (0.30 + 0.25 + 0.10) / (0.30 + 0.25 + 0.10) = 1.0.

    Interaction with Phase E: solo-viable candidates can now reach
    md=1.0 even on thumbnail libraries (cover hash not firing). That
    means the Phase E `solo_confidence_threshold` (default 0.95) is
    where silent-failure protection lives. Users who calibrate against
    thumbnail-only libraries should be aware that solo CV matches with
    all available signals at 1.0 will auto-write under default
    settings.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    if profile.series and candidate.summary.series:
        weighted_sum += W_SERIES * s_series(profile, candidate)
        total_weight += W_SERIES

    # Issue: profile carries either the raw string `issue` (e.g. "001")
    # or the parsed `issue_int`. The candidate side just has `issue`.
    profile_has_issue = bool(profile.issue) or profile.issue_int is not None
    if profile_has_issue and candidate.summary.issue:
        weighted_sum += W_ISSUE * s_issue(profile, candidate)
        total_weight += W_ISSUE

    if profile.year is not None and candidate.summary.year is not None:
        weighted_sum += W_YEAR * s_year(profile, candidate)
        total_weight += W_YEAR

    if profile.publisher and candidate.summary.publisher:
        weighted_sum += W_PUBLISHER * s_publisher(profile, candidate)
        total_weight += W_PUBLISHER

    if profile.page_count is not None and candidate.summary.page_count is not None:
        weighted_sum += W_PAGES * s_pages(profile, candidate)
        total_weight += W_PAGES

    if total_weight == 0.0:
        # No signal at all — neither side has data we can compare.
        return 0.0
    return weighted_sum / total_weight


def final_score(candidate: Candidate, *, hash_used: bool) -> float:
    """
    Blend metadata and cover scores. Cover-only-when-hashing case.

    Phase K note: `metadata_score` now renormalises over contributing
    signals, so for hashed candidates the blended formula stays the
    same — `_METADATA_WEIGHT_SUM` (0.80) is still the metadata's
    share of the blended budget, regardless of which signals
    contributed to producing the md value.
    """
    if not hash_used or candidate.cover_score is None:
        return candidate.metadata_score
    return (
        _METADATA_WEIGHT_SUM * candidate.metadata_score
        + W_COVER * candidate.cover_score
    )


def _policy_auto_writes(
    policy: Policy,
    *,
    top_score: float,
    gap: float,
    confidence_threshold: float,
    disambiguation_margin: float,
    solo_viable: bool,
    solo_confidence_threshold: float,
) -> bool:
    """
    Encode the four policy levels' auto-write rules.

    Containment holds: `strict ⊂ normal ⊂ eager`. `always-prompt` never
    auto-writes (the deferred path falls to PROMPT or SKIP).

    The `solo_viable` carve-out under NORMAL/EAGER is gated by
    `solo_confidence_threshold` (Phase E). Below the floor, a lone
    viable candidate does NOT auto-write — it falls through to PROMPT.
    The pre-Phase-E behavior is recoverable by setting the threshold
    to `min_confidence` (default 0.50), which makes any solo candidate
    above the min_confidence bar auto-write.
    """
    unambig = top_score >= confidence_threshold and gap >= disambiguation_margin
    # Solo-viable auto-write requires the lone candidate clear the floor.
    # Default floor = global confidence threshold, so NORMAL/EAGER's solo
    # path is no more permissive than STRICT unless the user opts in
    # by lowering the per-source override.
    solo_viable_confident = solo_viable and top_score >= solo_confidence_threshold
    match policy:
        case Policy.ALWAYS_PROMPT:
            return False
        case Policy.STRICT:
            return unambig
        case Policy.NORMAL:
            return unambig or solo_viable_confident
        case Policy.EAGER:
            return top_score >= confidence_threshold or solo_viable_confident


def _resolve_policy(
    ranked: list[Candidate],
    settings: OnlineSettings,
    source_name: str,
) -> Resolution:
    """
    Apply the Match Resolution Policy.

    Per-source overrides for `policy`, `confidence_threshold`,
    `min_confidence`, and `disambiguation_margin` are resolved here so the
    same matcher can serve multiple sources with different settings.
    """
    policy = resolve_policy(settings, source_name)
    threshold = resolve_confidence_threshold(settings, source_name)
    min_confidence = resolve_min_confidence(settings, source_name)
    margin = resolve_disambiguation_margin(settings, source_name)
    solo_threshold = resolve_solo_confidence_threshold(settings, source_name)

    if not ranked or ranked[0].score < min_confidence:
        if ranked:
            logger.info(
                f"online: no match cleared min_confidence "
                f"(top={ranked[0].score:.2f}, threshold={min_confidence:.2f})"
            )
        return Resolution(ResolutionKind.NO_MATCH, None, tuple(ranked))

    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    gap = (top.score - runner_up.score) if runner_up else 1.0
    viable = [c for c in ranked if c.score >= min_confidence]
    solo_viable = len(viable) == 1

    if _policy_auto_writes(
        policy,
        top_score=top.score,
        gap=gap,
        confidence_threshold=threshold,
        disambiguation_margin=margin,
        solo_viable=solo_viable,
        solo_confidence_threshold=solo_threshold,
    ):
        return Resolution(ResolutionKind.AUTO_WRITE, top, tuple(ranked))

    # Couldn't auto-write under this policy — defer to interactive/unattended.
    if settings.unattended:
        return Resolution(ResolutionKind.SKIP, None, tuple(ranked))
    return Resolution(ResolutionKind.PROMPT, None, tuple(ranked))


# Minimum number of top-ranked candidates to hash. For small candidate
# sets (≤ ~10 candidates), top-5 is enough to cover the realistic
# winners — broader hashing wastes cover-download budget.
_TOP_K_FOR_HASHING_MIN: Final[int] = 5

# Maximum number of candidates to hash. Caps cost on very large candidate
# sets (BALANCED budget over Watchmen-style multi-volume searches can
# return 15-25 candidates after pre-filter).
_TOP_K_FOR_HASHING_MAX: Final[int] = 15


def _top_k_for_hashing(candidate_count: int) -> int:
    """
    Adaptive cover-hash top-K (Phase J).

    The bigmedia 2026-05-14 calibration showed that Phase H's broaden
    retry caused 14 PROMPT-zone regressions: when broaden added
    candidates with similar metadata scores, the previously-best
    candidate dropped out of the fixed top-5 for hashing and lost its
    cover boost.

    Adaptive K scales with the candidate count — hash half the list,
    floored at 5 (the original constant), capped at 15 (cost budget).
    Cost: at most 10 extra cover-hash fetches per fixture vs the
    original K=5, only when the candidate set is genuinely large.
    Cache absorbs subsequent runs.

    Examples:
      5 candidates  → K=5  (current behavior; small set)
      10 candidates → K=5
      12 candidates → K=6
      20 candidates → K=10
      30 candidates → K=15 (capped)

    """
    return min(
        _TOP_K_FOR_HASHING_MAX, max(_TOP_K_FOR_HASHING_MIN, candidate_count // 2)
    )


# Tiebreak sentinel: candidates with no `volume_id` sort to the bottom of
# a score tie. We'd rather break ties in favor of *known*-canonical
# volumes than guess about unknown ones.
_NO_VOLUME_ID_TIEBREAK: int = 2**31


def _candidate_sort_key(c: Candidate) -> tuple[float, int, int]:
    """
    Tuple sort key with deterministic tiebreaks for ranked candidates.

    Components, ascending so smaller-tuple wins:

    1. ``-c.score`` — primary: blended score descending. The matcher's
       headline output.
    2. ``c.volume_id`` (or sentinel) — secondary: on a tied blended
       score, prefer the candidate from the *lower* volume id. CV
       creates the canonical volume first; later "Watchmen, 1987"
       volumes that share a name with the original are duplicates,
       regional editions, or admin oversights. None → sentinel so
       known volumes win against unknowns.
    3. ``c.issue_id`` — tertiary: on tied score AND tied volume_id
       (within-volume variant cover dupes), prefer the lower issue id.
       Same logic — the canonical issue record is the one created
       first.

    Without explicit tiebreakers Python's stable sort preserves the
    order the source returned candidates in, which lets the API's
    iteration order decide the matcher's verdict on ties. That's
    arbitrary and the wrong source of authority for tag writes.
    """
    return (
        -c.score,
        c.volume_id if c.volume_id is not None else _NO_VOLUME_ID_TIEBREAK,
        c.issue_id,
    )


# Maximum blended-score gap inside which the volume_id tiebreak overrides
# a slight cover-hash difference. The matcher's `disambiguation_margin`
# (0.10) is the policy threshold for "ambiguous"; this is roughly half
# of that — within which we treat metadata-identical candidates as
# effectively tied even if cover-hash nudged their blended scores apart.
#
# Why this matters: Watchmen (1987) #009 has two CV records — vol=3622
# (canonical) and vol=79545 (dupe). Both score md=0.91. Cover-hash
# rounds out at 0.81 vs 0.84 because of cover-image variance, blended
# diverges by ~0.006 (displayed 0.01). The plain sort picks vol=79545
# because its blended score is fractionally higher; with this
# correction, when metadata is identical the cover-hash signal isn't
# strong enough on its own to overrule the canonical-volume preference.
_TIED_METADATA_BLEND_MARGIN: float = 0.02

# Cover-score difference thresholds for the tied-metadata tiebreak.
# Phase I (2026-05-14) replaced the original absolute-threshold approach
# with a quality-relative one: a fixed-size diff means different things
# at different score levels.
#
# **The intuition.** When both candidates score very high (≥0.95), the
# Hamming distance from the local cover is tiny for both — under 1 bit
# out of 64. A 0.03 diff in that regime is meaningful (one is genuinely
# a tighter match). When both score medium (0.80-0.94), each has ~2
# bits of imprecision baked in — small diffs are hash variance from
# scan/JPEG/crop noise. The signal-vs-noise ratio inverts with the
# score level.
#
# **The formula.** A cover-diff is noise iff BOTH:
#   - `diff < _COVER_DIFF_ABSOLUTE_SIGNAL`: any diff above this is
#     always real signal (e.g., 0.59 vs 1.00 on the Hilda case — two
#     genuinely different covers).
#   - `diff / (1 - min_cover_score) < _COVER_DIFF_RELATIVE_THRESHOLD`:
#     the diff is a small fraction of the "room to perfect" the worse
#     candidate has. Room = how far the WORSE candidate sits from 1.0;
#     a diff that uses up half or more of that room is significant.
#
# **Empirical anchors** (from bigmedia 2026-05-14):
#   Hawkeye Freefall:   min=0.94, diff=0.03, room=0.06, ratio=0.50 → SIGNAL ✓
#   Watchmen #009 dup:  min=0.81, diff=0.03, room=0.19, ratio=0.16 → NOISE ✓
#   Original Sin dup:   min=0.91, diff=0.09, room=0.09, ratio=1.00 → SIGNAL ✓
#   Hilda Stone Forest: min=0.59, diff=0.41                        → SIGNAL via absolute floor
#   Fallen Son tied:    min=0.50, diff=0.00, room=0.50, ratio=0.00 → NOISE ✓
#
# Hawkeye is the case Phase G's tighter-absolute approach couldn't fix:
# with min=0.94, the 0.03 diff is a full half of the 0.06 room to
# perfect — clearly meaningful when both candidates are essentially
# matches. Watchmen's 0.03 diff at min=0.81 is only 16% of the room —
# scan noise.
_COVER_DIFF_ABSOLUTE_SIGNAL: float = 0.10
_COVER_DIFF_RELATIVE_THRESHOLD: float = 0.5


def _cover_diff_is_noise(a: Candidate, b: Candidate) -> bool:
    """
    Decide whether the cover-score gap between two candidates is hash noise.

    Returns True when the gap is small enough to be hash artifact rather
    than disambiguation signal. When either candidate's cover_score is
    missing, we can't compute a diff — fall back to "noise" so the
    volume_id tiebreak still applies (no cover signal at all means
    cover wasn't helping anyway).

    Phase I uses a quality-relative threshold (see module-level
    docstring on `_COVER_DIFF_ABSOLUTE_SIGNAL` and
    `_COVER_DIFF_RELATIVE_THRESHOLD` for the math). Replaces Phase G's
    simple absolute threshold which couldn't separate the Hawkeye case
    (signal at high-quality cover scores) from the Watchmen case
    (noise at medium-quality cover scores).
    """
    if a.cover_score is None or b.cover_score is None:
        return True
    diff = abs(a.cover_score - b.cover_score)
    # Above the absolute signal floor → always real signal, regardless
    # of where on the cover-score range the candidates sit.
    if diff >= _COVER_DIFF_ABSOLUTE_SIGNAL:
        return False
    # Relative threshold: how much of the "room to perfect" the worse
    # candidate's score is doing the diff use up? Using `min` (not max)
    # so a candidate at 1.00 vs one at 0.91 yields room=0.09, ratio=1.0
    # (signal) — the asymmetric Original Sin case.
    min_score = min(a.cover_score, b.cover_score)
    room_to_perfect = 1.0 - min_score
    if room_to_perfect <= 0.0:
        # Both at 1.00 — diff is hash precision artifact.
        return True
    return (diff / room_to_perfect) < _COVER_DIFF_RELATIVE_THRESHOLD


def _apply_tied_metadata_tiebreak(ranked: list[Candidate]) -> list[Candidate]:
    """
    Within same-metadata, near-blended-score groups, prefer lower volume_id.

    Walks the score-sorted list looking for consecutive candidates with
    *identical* `metadata_score` whose blended `score` differs by at
    most `_TIED_METADATA_BLEND_MARGIN` AND whose `cover_score` differs by
    at most `_COVER_DIFF_NOISE_MARGIN`. Within each such group, re-sorts
    by ``(volume_id, issue_id)`` ascending so the canonical record wins
    over near-tied dupes from later volumes.

    Conservative on three axes:

    - Requires *exact* metadata-score equality. Different metadata
      means the cover-hash signal is doing legitimate disambiguation
      work, and we should respect its blended-score outcome.
    - Requires blended scores within a small margin. Genuine
      score-spread (>0.02) means the matcher distinguished the
      candidates and we should trust that.
    - Requires cover-score difference to be noise-level (<=0.05). When
      one candidate's cover is a near-perfect Hamming match and the
      other's is materially worse, that's the cover signal doing real
      work — don't override.

    The three predicates together catch the "two records, same series +
    issue + year + publisher, different volume, near-identical covers"
    duplicate case (Watchmen #005, #009) without touching cases where
    the matcher's signals genuinely rank the candidates differently
    (Original Sin #001 — different cover scores, the better hash wins).
    """
    if len(ranked) < 2:  # noqa: PLR2004 — need at least 2 to compare adjacents
        return ranked

    result: list[Candidate] = []
    i = 0
    while i < len(ranked):
        # Group consecutive candidates with same metadata_score, close
        # blended score, AND noise-level cover-score difference relative
        # to the group leader.
        j = i + 1
        while (
            j < len(ranked)
            and ranked[j].metadata_score == ranked[i].metadata_score
            and ranked[i].score - ranked[j].score <= _TIED_METADATA_BLEND_MARGIN
            and _cover_diff_is_noise(ranked[i], ranked[j])
        ):
            j += 1
        group = ranked[i:j]
        if len(group) > 1:
            group = sorted(
                group,
                key=lambda c: (
                    c.volume_id if c.volume_id is not None else _NO_VOLUME_ID_TIEBREAK,
                    c.issue_id,
                ),
            )
        result.extend(group)
        i = j
    return result


def _should_invoke_hashing(
    metadata_ranked: list[Candidate],
    threshold: float,
    *,
    min_confidence: float,
    disambiguation_margin: float,
) -> bool:
    """
    Decide whether to invoke cover hashing on the top candidates.

    Skip when the top is unambiguous (above threshold AND well-separated)
    or when nothing clears `min_confidence`.
    """
    if not metadata_ranked:
        return False
    top = metadata_ranked[0]
    if top.metadata_score < min_confidence:
        return False
    runner_up = metadata_ranked[1] if len(metadata_ranked) > 1 else None
    gap = (top.metadata_score - runner_up.metadata_score) if runner_up else 1.0
    return not (top.metadata_score >= threshold and gap >= disambiguation_margin)


def _resolve_candidate_hash(
    candidate: Candidate,
    candidate_hash_fetcher: CandidateHashFetcher | None,
) -> str | None:
    """Get a candidate's pHash, preferring precomputed value."""
    if candidate.precomputed_cover_hash:
        return candidate.precomputed_cover_hash
    if candidate_hash_fetcher is None:
        return None
    cover_url = candidate.summary.cover_url
    if not cover_url:
        return None
    try:
        return candidate_hash_fetcher(cover_url)
    except Exception as exc:
        logger.warning(
            f"online: cover-hash fetcher failed for {candidate.source}:"
            f"{candidate.issue_id} (url={cover_url}): {exc}"
        )
        return None


def _apply_cover_hashing(
    ranked: list[Candidate],
    local_hash: str,
    candidate_hash_fetcher: CandidateHashFetcher | None,
) -> list[Candidate]:
    """
    Hash the top K candidates and re-rank by blended score.

    K is adaptive (Phase J — see `_top_k_for_hashing`): for small
    candidate sets it stays at 5 (the historical constant); for larger
    sets (Phase H broaden-retry, BALANCED budget) it scales up to 15.
    """
    top_k = _top_k_for_hashing(len(ranked))
    rescored: list[Candidate] = []
    for i, c in enumerate(ranked):
        if i >= top_k:
            rescored.append(c)
            continue
        cand_hash = _resolve_candidate_hash(c, candidate_hash_fetcher)
        if not cand_hash:
            rescored.append(c)
            continue
        try:
            cs = _cover_score(local_hash, cand_hash)
        except Exception as exc:
            logger.warning(
                f"online: cover hash failed for {c.source}:{c.issue_id}: {exc}"
            )
            rescored.append(c)
            continue
        with_cover = replace(c, cover_score=cs)
        rescored.append(
            replace(with_cover, score=final_score(with_cover, hash_used=True))
        )
    rescored.sort(key=_candidate_sort_key)
    return _apply_tied_metadata_tiebreak(rescored)


class OnlineMatcher:
    """Stateless ranker + policy resolver."""

    def rank(
        self,
        profile: ComicProfile,
        candidates: list[Candidate],
        *,
        local_hash_provider: LocalHashProvider | None = None,
        candidate_hash_fetcher: CandidateHashFetcher | None = None,
        threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        min_confidence: float = 0.50,
        disambiguation_margin: float = 0.10,
    ) -> list[Candidate]:
        """
        Score every candidate and return them sorted descending by score.

        When `local_hash_provider` is provided and the metadata-only
        ranking is ambiguous (top below threshold or close call), invokes
        cover hashing on the top K candidates and re-ranks. Metron
        candidates carry a `precomputed_cover_hash` (string-compare); other
        sources fall through to ``candidate_hash_fetcher`` for
        download-and-hash with caching. Both kinds mix in the same ranking.
        """
        scored: list[Candidate] = []
        for c in candidates:
            md = metadata_score(profile, c)
            with_md = replace(c, metadata_score=md)
            scored.append(replace(with_md, score=final_score(with_md, hash_used=False)))
        scored.sort(key=_candidate_sort_key)
        scored = _apply_tied_metadata_tiebreak(scored)

        if local_hash_provider is None or not _should_invoke_hashing(
            scored,
            threshold,
            min_confidence=min_confidence,
            disambiguation_margin=disambiguation_margin,
        ):
            return scored

        local_hash = local_hash_provider()
        if not local_hash:
            return scored
        return _apply_cover_hashing(scored, local_hash, candidate_hash_fetcher)

    def resolve(
        self,
        ranked: list[Candidate],
        settings: OnlineSettings,
        source_name: str,
    ) -> Resolution:
        """
        Apply the Match Resolution Policy.

        ``source_name`` selects per-source overrides for `policy`,
        `confidence_threshold`, `min_confidence`, and
        `disambiguation_margin` (all fall back to the global setting if
        no per-source override is set).
        """
        return _resolve_policy(ranked, settings, source_name)
