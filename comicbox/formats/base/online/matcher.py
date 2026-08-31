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
    DEFAULT_AUTO_THRESHOLD,
    MatchMode,
    resolve_auto_threshold,
    resolve_disambiguation_margin,
    resolve_match,
    resolve_min_confidence,
    resolve_solo_threshold,
)
from comicbox.formats.base.online.cover_hash import cover_score as _cover_score
from comicbox.formats.base.online.signals import (
    s_issue,
    s_pages,
    s_publisher,
    s_series,
    s_year,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.config.settings import OnlineSettings
    from comicbox.formats.base.online.profile import Candidate, ComicProfile


# Callable that returns the local comic's pHash hex (or None if unavailable).
LocalHashProvider = Callable[[], str | None]

# Callable that fetches and hashes a candidate cover URL, with caching.
# Returns the hex hash string or None if unavailable.
CandidateHashFetcher = Callable[[str], str | None]

# Callable that resolves MANY candidate cover URLs at once, returning
# `{url: hash}` for the ones that resolved. Absent keys mean "no hash for
# that cover" — same meaning as `CandidateHashFetcher` returning None.
# Supplying this lets the whole top-K download concurrently instead of
# one blocking round-trip per candidate; see
# `comicbox.formats.base.online.cover_hash.CoverFetchPool`.
CandidateHashBatchFetcher = Callable[["Sequence[str]"], "dict[str, str]"]


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
_DEFAULT_CONFIDENCE_THRESHOLD = DEFAULT_AUTO_THRESHOLD


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

    Phase K rev 2 (2026-05-14): a signal contributes when EITHER side
    has data. The total is renormalised over the contributing weights.
    Signals are skipped only when BOTH sides are empty/None — i.e. there
    is genuinely no comparison to make.

    Why this matters:

    1. CV's `BasicIssue` (what `search` returns) doesn't expose
       publisher or page_count. Under the original formula those signals
       returned weak-prior values (0.5/0.6) that diluted the score even
       when series/issue/year all matched perfectly. A thumbnail-library
       comic with no profile-side publisher / pages would prompt for an
       otherwise-obvious match ("Wolverine #20 (2026)" → md capped at
       0.91 < confidence_threshold 0.95).

    2. The fix is to renormalise — but only over the signals where data
       exists *on at least one side*. Truly-symmetric absence (both
       profile and candidate missing publisher) is dropped from the
       denominator. Asymmetric absence (profile knows year, candidate
       doesn't) keeps the signal in the denominator and lets the
       signal function's missing-data branch (s_year=0.3,
       s_publisher=0.5, s_pages=0.6) penalise the under-informed
       candidate.

    Phase K rev 1 (the first cut of this function) skipped on EITHER
    side missing, which incorrectly lifted CV BasicIssue candidates with
    a null `cover_date` to md=1.0 over the actually-matching trade
    collection. Caught by bigmedia calibration: "Conan the Barbarian by
    Jim Zub: Land of the Lotus (2021)" preferred a 1.0-scored canonical
    Conan record with year=None over the year=2021 trade-collection
    record. Rev 2 keeps asymmetric signals; only both-None disappears.

    Interaction with Phase E: solo-viable candidates can still reach
    md=1.0 in the symmetric-missing case (Wolverine prompt fix). For
    libraries with full profile metadata (publisher / page_count
    present), the asymmetric-skip stays as the s_publisher=0.5 /
    s_pages=0.6 weak prior, matching pre-Phase-K behaviour. So Phase E's
    `solo_confidence_threshold` is the load-bearing protection only on
    thumbnail-library calibration runs.
    """
    # Skip a signal only when BOTH sides are empty (truly no data on
    # either side). When asymmetric — profile has data, candidate doesn't
    # or vice versa — keep the signal so its function's missing-data
    # branch (s_year=0.3, s_publisher=0.5, s_pages=0.6, s_series=0.0,
    # s_issue=0.5) penalises the candidate rather than letting it coast.
    # Skipping asymmetric cases was the Phase K rev-1 bug: CV BasicIssue
    # candidates with year=None / publisher=None won over candidates that
    # actually matched the profile's year, because their missing-data
    # signals got dropped from the renormalisation denominator.
    signals = _contributing_signals(profile, candidate)
    weighted_sum = sum(
        weight * scorer(profile, candidate) for weight, scorer in signals
    )
    total_weight = sum(weight for weight, _ in signals)
    if total_weight == 0.0:
        # No signal at all — neither side has data we can compare.
        return 0.0
    return weighted_sum / total_weight


def _contributing_signals(
    profile: ComicProfile, candidate: Candidate
) -> tuple[tuple[float, Callable[..., float]], ...]:
    """Yield (weight, scorer) for each signal where at least one side has data."""
    # Issue: profile carries either the raw string `issue` (e.g. "001")
    # or the parsed `issue_int`. The candidate side just has `issue`.
    profile_has_issue = bool(profile.issue) or profile.issue_int is not None
    # Series: alternative names count as candidate series data — `s_series`
    # scores them, so dropping the signal would take W_SERIES out of the
    # renormalisation denominator and inflate the rest.
    summary = candidate.summary
    return tuple(
        (weight, scorer)
        for contributes, weight, scorer in (
            (
                bool(profile.series or summary.series or summary.alt_series),
                W_SERIES,
                s_series,
            ),
            (profile_has_issue or bool(summary.issue), W_ISSUE, s_issue),
            (profile.year is not None or summary.year is not None, W_YEAR, s_year),
            (bool(profile.publisher or summary.publisher), W_PUBLISHER, s_publisher),
            (
                profile.page_count is not None or summary.page_count is not None,
                W_PAGES,
                s_pages,
            ),
        )
        if contributes
    )


def final_score(candidate: Candidate, *, hash_used: bool) -> float:
    """
    Blend metadata and cover scores. Cover-only-when-hashing case.

    Phase K note: `metadata_score` now renormalises over contributing
    signals, so for hashed candidates the blended formula stays the
    same — `_METADATA_WEIGHT_SUM` (0.80) is still the metadata's
    share of the blended budget, regardless of which signals
    contributed to producing the md value.

    Known asymmetry (audited 2026-08-31, deliberately not retuned here
    — see the matcher scoring audit under
    ``tasks/online-tagging/calibration-notes/``): an un-hashed
    candidate is scored on raw metadata while a hashed one is scored on
    `0.80*md + 0.20*cover`, and both are compared against the same
    `auto_threshold`. Measuring a cover therefore *moves* the bar a
    candidate has to clear: it holds a bar T only while
    `cover >= (T - 0.80*md) / 0.20`. At the shipped T=0.95 that is
    cover >= 0.75 for a flawless md=1.0, and unreachable for any
    md < 0.9375 — while an un-hashed sibling with the same metadata
    keeps its md and clears T unmeasured. In the 2026-05-17 bigmedia
    run 48% of 548 measured cover scores were below 0.75, and the
    blend lowered the top candidate's score in 114 of 306 hashed
    fixtures. Retuning the weights (or renormalising the un-hashed
    side) changes which files get written to, so it needs a
    calibration run, not a patch.
    """
    if not hash_used or candidate.cover_score is None:
        return candidate.metadata_score
    return (
        _METADATA_WEIGHT_SUM * candidate.metadata_score
        + W_COVER * candidate.cover_score
    )


def _policy_auto_writes(
    policy: MatchMode,
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

    Containment holds: `careful ⊂ auto ⊂ eager`. `ask` never
    auto-writes (the deferred path falls to PROMPT or SKIP).

    The `solo_viable` carve-out under AUTO/EAGER is gated by
    `solo_confidence_threshold` (Phase E). Below the floor, a lone
    viable candidate does NOT auto-write — it falls through to PROMPT.
    The pre-Phase-E behavior is recoverable by setting the threshold
    to `min_confidence` (default 0.50), which makes any solo candidate
    above the min_confidence bar auto-write.

    The floor defaults to this source's resolved `auto_threshold`
    (``resolve_solo_threshold``), and at that default the carve-out is
    subsumed: `solo_viable` means every other candidate is below
    `min_confidence` (0.50), so a top clearing a >= 0.50 threshold is
    also more than `disambiguation_margin` clear of the runner-up, i.e.
    already `unambig`. AUTO therefore behaves exactly like CAREFUL out
    of the box; the carve-out only widens it once a user lowers
    `solo_threshold` for a source. That is the intended reading of
    "no more permissive than CAREFUL unless the user opts in" — not a
    dead branch to delete.
    """
    unambig = top_score >= confidence_threshold and gap >= disambiguation_margin
    # Solo-viable auto-write requires the lone candidate clear the floor.
    # Default floor = this source's auto-write threshold, so AUTO/EAGER's
    # solo path is no more permissive than CAREFUL unless the user opts in
    # by lowering the per-source override.
    solo_viable_confident = solo_viable and top_score >= solo_confidence_threshold
    match policy:
        case MatchMode.ASK:
            return False
        case MatchMode.CAREFUL:
            return unambig
        case MatchMode.AUTO:
            return unambig or solo_viable_confident
        case MatchMode.EAGER:
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
    policy = resolve_match(settings, source_name)
    threshold = resolve_auto_threshold(settings, source_name)
    min_confidence = resolve_min_confidence(settings, source_name)
    margin = resolve_disambiguation_margin(settings, source_name)
    solo_threshold = resolve_solo_threshold(settings, source_name)

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
    from comicbox.config.settings import Prompts

    if settings.lookup.prompts is Prompts.NEVER:
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

    K scales with the candidate count — hash half the list, floored at
    5 (the original fixed constant), capped at 15 (cost budget). Cost:
    at most 10 extra cover-hash fetches per fixture vs the original
    K=5, and only when the candidate set is genuinely large. The cache
    absorbs subsequent runs.

    Phase J was written to stop a large candidate set from pushing the
    best candidate out of a fixed top-5 and costing it its cover boost.
    The feature that produced those large sets — Phase H's broaden
    retry — was reverted (`62a5725`, `b407815`), and Phase J itself
    flipped zero outcomes on the corpus that motivated it. It stays as
    a cost-bounded generalization of K=5 for any future feature that
    returns wide candidate lists; a rank-boundary artifact is still a
    real failure mode (see `_cover_diff_is_noise`), just not one this
    corpus exercises.

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

# Maximum cover-score difference treated as hash noise rather than a
# real disambiguation signal. ~2 Hamming bits out of 64 (pHash range).
# Below this, cover-score variation is hash artifact / variant-cover
# wobble. Above it, one candidate's cover is materially more similar to
# the local than the other's — that's a real signal we should respect.
#
# Specifically: Original Sin (2014) #001 has two records, md=0.91 both;
# one at cover=1.00 (perfect Hamming match), one at cover=0.91 (close
# but not identical). The 0.09 cover gap IS the signal — the right
# answer's cover is genuinely a better match. Without this guard, the
# tiebreak collapses them and the lower vol_id wins, which is wrong.
#
# Phase G (2026-05-14) tightened this from 0.05 to 0.03 against the
# bigmedia calibration; 0.02 would also catch Hawkeye Freefall (cover
# diff exactly 0.03) but risks breaking the Watchmen canonical-volume
# tiebreak, so the boundary stayed conservative. The run-by-run
# reasoning lives in `tasks/online-tagging/calibration-notes/`.
_COVER_DIFF_NOISE_MARGIN: float = 0.03


def _cover_diff_is_noise(a: Candidate, b: Candidate) -> bool:
    """
    Decide whether the cover-score gap between two candidates is hash noise.

    Returns True when the gap is small enough to be hash artifact
    rather than disambiguation signal, so the volume_id tiebreak can
    override it.

    A missing `cover_score` is not one case but two, and they answer
    this question differently:

    - **No cover signal to be had.** Neither candidate was hashed
      (hashing never fired), or the one that wasn't scored *was*
      hashed and came back empty — no `cover_url`, a fetch failure, an
      undecodable image. Cover genuinely isn't helping here, so treat
      the pair as tied and let volume_id decide, as before.
    - **Not computed.** The unscored candidate sits outside the
      hashing top-K (`_top_k_for_hashing`), so its cover was never
      looked at. Its silence is our cost cap talking, not evidence of
      similarity — and collapsing the pair would let a candidate no
      one measured beat one whose cover we *did* measure against the
      local copy, on volume id alone. Keep the measured signal: not
      noise.

    The second case needs at least 6 candidates to arise (K >= 5) plus
    an exact metadata-score tie across the K boundary, so it is narrow
    — but it is the one case where the tiebreak discards a real
    measurement instead of breaking a real tie.
    """
    if a.cover_score is not None and b.cover_score is not None:
        return abs(a.cover_score - b.cover_score) <= _COVER_DIFF_NOISE_MARGIN
    if a.cover_score is None and b.cover_score is None:
        # No cover signal on either side — nothing for the tiebreak to
        # override, so let volume_id decide as it always has.
        return True
    unmeasured = a if a.cover_score is None else b
    # One side measured. Its signal stands unless the other side was
    # examined too and simply had no usable cover.
    return unmeasured.cover_hash_attempted


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
    - Requires the cover-score difference to be noise-level
      (`_COVER_DIFF_NOISE_MARGIN`, 0.03), with an unmeasured cover
      counting as noise only when nothing was measured for it to hide
      behind (`_cover_diff_is_noise`). When one candidate's cover is a
      near-perfect Hamming match and the other's is materially worse,
      that's the cover signal doing real work — don't override.

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
    prefetched: dict[str, str] | None = None,
) -> str | None:
    """
    Get a candidate's pHash, preferring precomputed value.

    ``prefetched`` is the batch pre-pass's `{url: hash}` map. A URL
    present there is answered without touching the network; a URL the
    batch pass already tried and failed is absent from the map, and
    since the batch covered every hashable candidate in the top-K,
    absence means "no hash" rather than "not looked at yet" — so we do
    NOT fall back to a per-URL fetch and re-pay the failed download.
    """
    if candidate.precomputed_cover_hash:
        return candidate.precomputed_cover_hash
    cover_url = candidate.summary.cover_url
    if not cover_url:
        return None
    if prefetched is not None:
        return prefetched.get(cover_url)
    if candidate_hash_fetcher is None:
        return None
    try:
        return candidate_hash_fetcher(cover_url)
    except Exception as exc:
        logger.warning(
            f"online: cover-hash fetcher failed for {candidate.source}:"
            f"{candidate.issue_id} (url={cover_url}): {exc}"
        )
        return None


def _prefetch_candidate_hashes(
    ranked: list[Candidate],
    top_k: int,
    candidate_hash_batch_fetcher: CandidateHashBatchFetcher,
) -> dict[str, str]:
    """
    Resolve every hashable top-K cover in ONE batch call.

    The candidates that need a download are exactly those inside the
    top-K with a cover URL and no precomputed hash. Collecting them
    upfront lets the fetcher run them concurrently over a shared HTTP
    client and answer the cache in a single query, instead of the
    serial download-per-candidate the scoring loop used to drive.

    A failing batch degrades to an empty map, which the scoring loop
    reads as "no cover signal" — the same outcome the serial path
    produced when every download failed.
    """
    urls = [
        url
        for c in ranked[:top_k]
        if not c.precomputed_cover_hash and (url := c.summary.cover_url)
    ]
    if not urls:
        return {}
    try:
        return candidate_hash_batch_fetcher(urls)
    except Exception as exc:
        logger.warning(f"online: batch cover-hash fetch failed: {exc}")
        return {}


def _apply_cover_hashing(
    ranked: list[Candidate],
    local_hash: str,
    candidate_hash_fetcher: CandidateHashFetcher | None,
    candidate_hash_batch_fetcher: CandidateHashBatchFetcher | None = None,
) -> list[Candidate]:
    """
    Hash the top K candidates and re-rank by blended score.

    K is adaptive (Phase J — see `_top_k_for_hashing`): for small
    candidate sets it stays at 5 (the historical constant); for larger
    sets (a BALANCED / THOROUGH budget over a multi-volume search) it
    scales up to 15. Candidates inside K are marked
    `cover_hash_attempted` whether or not a hash came back, so the
    tiebreak can tell "this cover doesn't help" from "we never looked".

    When a batch fetcher is supplied, every download for the top-K is
    issued up front and concurrently (`_prefetch_candidate_hashes`);
    the loop below then only scores. Ordering, scoring and the tiebreak
    are identical either way — only *when* the bytes arrive changes.
    """
    top_k = _top_k_for_hashing(len(ranked))
    prefetched = (
        _prefetch_candidate_hashes(ranked, top_k, candidate_hash_batch_fetcher)
        if candidate_hash_batch_fetcher is not None
        else None
    )
    rescored: list[Candidate] = []
    for i, c in enumerate(ranked):
        if i >= top_k:
            rescored.append(c)
            continue
        # Attempted from here on, whatever the outcome — the tiebreak
        # reads this to tell an unhelpful cover from an unexamined one.
        attempted = replace(c, cover_hash_attempted=True)
        cand_hash = _resolve_candidate_hash(c, candidate_hash_fetcher, prefetched)
        if not cand_hash:
            rescored.append(attempted)
            continue
        try:
            cs = _cover_score(local_hash, cand_hash)
        except Exception as exc:
            logger.warning(
                f"online: cover hash failed for {c.source}:{c.issue_id}: {exc}"
            )
            rescored.append(attempted)
            continue
        with_cover = replace(attempted, cover_score=cs)
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
        candidate_hash_batch_fetcher: CandidateHashBatchFetcher | None = None,
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

        ``candidate_hash_batch_fetcher``, when supplied, takes precedence
        for the download path: the whole top-K is resolved in one
        concurrent batch rather than one blocking GET at a time. The
        ranking it produces is identical.
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
        return _apply_cover_hashing(
            scored, local_hash, candidate_hash_fetcher, candidate_hash_batch_fetcher
        )

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
