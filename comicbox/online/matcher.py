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

# Internal constants (not user-exposed for now per Phase 4 review).
_MIN_CONFIDENCE = 0.50
_DISAMBIGUATION_MARGIN = 0.10


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
    return _METADATA_WEIGHT_SUM * candidate.metadata_score + W_COVER * candidate.cover_score


def _is_unambiguous_top(top_score: float, gap: float, threshold: float) -> bool:
    return top_score >= threshold and gap >= _DISAMBIGUATION_MARGIN


def _resolve_unattended_combined(
    viable: list[Candidate], ranked: list[Candidate]
) -> Resolution:
    """Both --accept-only and --skip-multiple set."""
    if len(viable) == 1:
        return Resolution(ResolutionKind.AUTO_WRITE, viable[0], tuple(ranked))
    return Resolution(ResolutionKind.SKIP, None, tuple(ranked))


def _resolve_accept_only(
    viable: list[Candidate], ranked: list[Candidate]
) -> Resolution:
    if len(viable) == 1:
        return Resolution(ResolutionKind.AUTO_WRITE, viable[0], tuple(ranked))
    return Resolution(ResolutionKind.PROMPT, None, tuple(ranked))


def _resolve_skip_multiple(
    viable: list[Candidate], ranked: list[Candidate]
) -> Resolution:
    if len(viable) > 1:
        return Resolution(ResolutionKind.SKIP, None, tuple(ranked))
    return Resolution(ResolutionKind.PROMPT, None, tuple(ranked))


def _resolve_policy(
    ranked: list[Candidate], settings: OnlineSettings
) -> Resolution:
    if not ranked or ranked[0].score < _MIN_CONFIDENCE:
        if ranked:
            logger.info(
                f"online: no match cleared min_confidence "
                f"(top={ranked[0].score:.2f})"
            )
        return Resolution(ResolutionKind.NO_MATCH, None, tuple(ranked))

    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    gap = (top.score - runner_up.score) if runner_up else 1.0

    if _is_unambiguous_top(top.score, gap, settings.confidence_threshold):
        return Resolution(ResolutionKind.AUTO_WRITE, top, tuple(ranked))

    viable = [c for c in ranked if c.score >= _MIN_CONFIDENCE]
    if settings.skip_multiple and settings.accept_only:
        return _resolve_unattended_combined(viable, ranked)
    if settings.accept_only:
        return _resolve_accept_only(viable, ranked)
    if settings.skip_multiple:
        return _resolve_skip_multiple(viable, ranked)
    return Resolution(ResolutionKind.PROMPT, None, tuple(ranked))


_TOP_K_FOR_HASHING = 5


def _should_invoke_hashing(
    metadata_ranked: list[Candidate],
    threshold: float,
) -> bool:
    """
    Decide whether to invoke cover hashing on the top candidates.

    Skip when the top is unambiguous (above threshold AND well-separated)
    or when nothing clears `min_confidence`.
    """
    if not metadata_ranked:
        return False
    top = metadata_ranked[0]
    if top.metadata_score < _MIN_CONFIDENCE:
        return False
    runner_up = metadata_ranked[1] if len(metadata_ranked) > 1 else None
    gap = (top.metadata_score - runner_up.metadata_score) if runner_up else 1.0
    return not (top.metadata_score >= threshold and gap >= _DISAMBIGUATION_MARGIN)


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
        rescored.append(replace(with_cover, score=final_score(with_cover, hash_used=True)))
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
        threshold: float = 0.85,
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

        if local_hash_provider is None or not _should_invoke_hashing(scored, threshold):
            return scored

        local_hash = local_hash_provider()
        if not local_hash:
            return scored
        return _apply_cover_hashing(scored, local_hash, candidate_hash_fetcher)

    def resolve(
        self,
        ranked: list[Candidate],
        settings: OnlineSettings,
    ) -> Resolution:
        """Apply the Match Resolution Policy from Phase 2."""
        return _resolve_policy(ranked, settings)
