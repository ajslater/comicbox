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
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.config.settings import (
    Policy,
    resolve_confidence_threshold,
    resolve_disambiguation_margin,
    resolve_min_confidence,
    resolve_policy,
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
    """Renormalised weighted sum of metadata signals, in [0, 1]."""
    score = (
        s_series(profile, candidate) * W_SERIES
        + s_issue(profile, candidate) * W_ISSUE
        + s_year(profile, candidate) * W_YEAR
        + s_publisher(profile, candidate) * W_PUBLISHER
        + s_pages(profile, candidate) * W_PAGES
    )
    return score / _METADATA_WEIGHT_SUM


def final_score(candidate: Candidate, *, hash_used: bool) -> float:
    """Blend metadata and cover scores. Cover-only-when-hashing case."""
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
) -> bool:
    """
    Encode the four policy levels' auto-write rules.

    Containment holds: `strict ⊂ normal ⊂ eager`. `always-prompt` never
    auto-writes (the deferred path falls to PROMPT or SKIP).
    """
    unambig = top_score >= confidence_threshold and gap >= disambiguation_margin
    match policy:
        case Policy.ALWAYS_PROMPT:
            return False
        case Policy.STRICT:
            return unambig
        case Policy.NORMAL:
            return unambig or solo_viable
        case Policy.EAGER:
            return top_score >= confidence_threshold or solo_viable


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
    ):
        return Resolution(ResolutionKind.AUTO_WRITE, top, tuple(ranked))

    # Couldn't auto-write under this policy — defer to interactive/unattended.
    if settings.unattended:
        return Resolution(ResolutionKind.SKIP, None, tuple(ranked))
    return Resolution(ResolutionKind.PROMPT, None, tuple(ranked))


_TOP_K_FOR_HASHING = 5


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
    """Hash the top K candidates and re-rank by blended score."""
    rescored: list[Candidate] = []
    for i, c in enumerate(ranked):
        if i >= _TOP_K_FOR_HASHING:
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
    rescored.sort(key=lambda c: c.score, reverse=True)
    return rescored


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
        scored.sort(key=lambda c: c.score, reverse=True)

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
