"""
Matcher scoring: which bar a candidate is judged against.

The two halves of the 2026-08-31 scoring audit — what a missing cover
score means to the volume-id tiebreak, and the different scales hashed
and un-hashed candidates are scored on. See
``tasks/online-tagging/calibration-notes/2026-08-31-matcher-scoring-audit.md``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from comicbox.config.online.settings import (
    MatchMode,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineTuningSettings,
    Prompts,
)
from comicbox.formats.base.online.matcher import (
    OnlineMatcher,
    ResolutionKind,
    _apply_cover_hashing,
    _cover_diff_is_noise,
    final_score,
)
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)

_LOCAL_HASH = "0000000000000000"
# 32 of 64 bits differ from _LOCAL_HASH → cover_score 0.5.
_HALF_MATCH_HASH = "00000000ffffffff"
_COVER_URL = "http://example.com/cover.jpg"


def _profile() -> ComicProfile:
    return ComicProfile(
        series="Foo Comics",
        issue="5",
        issue_int=5,
        year=2020,
        publisher="Quality Comics",
        page_count=24,
    )


def _candidate(
    *,
    issue_id: int = 1,
    volume_id: int | None = None,
    page_count: int | None = 24,
    cover_url: str | None = None,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series="Foo Comics",
            issue="5",
            year=2020,
            publisher="Quality Comics",
            page_count=page_count,
            cover_url=cover_url,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


def _settings(*, auto_threshold: float, match: MatchMode) -> OnlineSettings:
    return OnlineSettings(
        lookup=OnlineLookupSettings(match=match, prompts=Prompts.ASK),
        tuning=OnlineTuningSettings(auto_threshold=auto_threshold),
    )


def _scored(
    *, issue_id: int, volume_id: int, metadata_score: float, cover_url: str | None
) -> Candidate:
    """Build a pre-scored candidate as `_apply_cover_hashing` receives them."""
    c = _candidate(issue_id=issue_id, volume_id=volume_id, cover_url=cover_url)
    return replace(c, metadata_score=metadata_score, score=metadata_score)


def _straddling_candidate_list(*, twin_cover_url: str | None) -> list[Candidate]:
    """
    Twelve candidates whose ranks 5 and 6 straddle the hashing top-K.

    K = 12 // 2 = 6, so rank 5 is hashed and rank 6 is not. The two
    carry identical metadata scores and differ only in volume id, with
    the *unhashed* twin holding the lower (canonical-looking) one — the
    shape where the volume_id tiebreak can discard a measured cover.
    """
    leaders = [
        _scored(issue_id=i, volume_id=i, metadata_score=0.95, cover_url=_COVER_URL)
        for i in range(5)
    ]
    measured = _scored(
        issue_id=10, volume_id=500, metadata_score=0.91, cover_url=_COVER_URL
    )
    twin = _scored(
        issue_id=20, volume_id=100, metadata_score=0.91, cover_url=twin_cover_url
    )
    tail = [
        _scored(
            issue_id=30 + i,
            volume_id=900 + i,
            metadata_score=0.60,
            cover_url=_COVER_URL,
        )
        for i in range(5)
    ]
    return [*leaders, measured, twin, *tail]


def _perfect_match_fetcher(url: str) -> str:
    del url
    return _LOCAL_HASH


# ------------- cover hash: "not computed" is not "no cover"


class TestCoverHashNotComputedVsUnavailable:
    """`cover_score is None` means two different things; they differ here."""

    def test_never_hashed_twin_does_not_collapse_a_measured_cover(self) -> None:
        """
        A candidate outside top-K can't win a tie on volume id alone.

        Rank 5's cover is a perfect Hamming match against the local
        copy; rank 6 has identical metadata, a lower volume id, and a
        cover nobody looked at because the adaptive top-K stopped one
        candidate short. Collapsing them treats "not computed" as "no
        signal" and hands the win to the unexamined record.
        """
        result = _apply_cover_hashing(
            _straddling_candidate_list(twin_cover_url=_COVER_URL),
            local_hash=_LOCAL_HASH,
            candidate_hash_fetcher=_perfect_match_fetcher,
        )

        measured, twin = result[5], result[6]
        assert measured.issue_id == 10
        assert measured.cover_score == 1.0
        assert measured.cover_hash_attempted
        # The twin was never examined: no score, and no attempt either.
        assert twin.issue_id == 20
        assert twin.cover_score is None
        assert not twin.cover_hash_attempted
        # Same metadata, blended gap inside the tie margin — the group
        # would have formed if the missing cover counted as noise.
        assert measured.metadata_score == twin.metadata_score
        assert 0 < measured.score - twin.score <= 0.02

    def test_hashed_twin_with_no_cover_still_yields_to_volume_id(self) -> None:
        """
        An examined candidate with no usable cover keeps the old fallback.

        Same shape, but the twin sits *inside* the hashing top-K with no
        `cover_url` at all. There is no cover signal to be had for it,
        so the canonical-volume preference decides, exactly as before.
        """
        candidates = _straddling_candidate_list(twin_cover_url=None)
        # Move the coverless twin inside K (rank 4) and a leader out.
        candidates[4], candidates[6] = candidates[6], candidates[4]

        result = _apply_cover_hashing(
            candidates,
            local_hash=_LOCAL_HASH,
            candidate_hash_fetcher=_perfect_match_fetcher,
        )

        twin, measured = result[5], result[6]
        assert twin.issue_id == 20
        assert twin.cover_score is None
        assert twin.cover_hash_attempted  # examined, just unusable
        assert measured.issue_id == 10
        # Lower volume id wins the tie, as it always has.
        assert twin.volume_id == 100
        assert measured.volume_id == 500

    def test_cover_diff_is_noise_tri_state(self) -> None:
        """The predicate directly, on all three shapes of a missing score."""
        measured = replace(_candidate(issue_id=1), cover_score=1.0)
        unexamined = replace(_candidate(issue_id=2), cover_hash_attempted=False)
        coverless = replace(_candidate(issue_id=3), cover_hash_attempted=True)
        close = replace(_candidate(issue_id=4), cover_score=0.98)
        far = replace(_candidate(issue_id=5), cover_score=0.80)

        # Two measured scores: the margin decides, in both orders.
        assert _cover_diff_is_noise(measured, close)
        assert not _cover_diff_is_noise(measured, far)
        assert not _cover_diff_is_noise(far, measured)
        # Neither measured: no signal at all.
        assert _cover_diff_is_noise(unexamined, coverless)
        # Measured vs examined-but-coverless: still no signal to compare.
        assert _cover_diff_is_noise(measured, coverless)
        assert _cover_diff_is_noise(coverless, measured)
        # Measured vs never-examined: the measurement stands.
        assert not _cover_diff_is_noise(measured, unexamined)
        assert not _cover_diff_is_noise(unexamined, measured)


# ------------- hashed / un-hashed scoring asymmetry (documented, not fixed)


class TestHashedUnhashedAsymmetry:
    """
    Measuring a cover moves the bar a candidate has to clear.

    Un-hashed candidates are scored on raw metadata; hashed ones on
    `0.80*md + 0.20*cover`. Both are compared against one
    `auto_threshold`. These tests pin the consequence so a future
    calibration run has a stated baseline to move — they are not an
    endorsement of the asymmetry.
    """

    def test_break_even_cover_for_the_shipped_bar(self) -> None:
        """A hashed candidate holds bar T only while cover >= (T - 0.8*md)/0.2."""
        perfect = replace(_candidate(), metadata_score=1.0, cover_score=0.75)
        assert final_score(perfect, hash_used=True) == pytest.approx(0.95)
        assert final_score(replace(perfect, cover_score=0.74), hash_used=True) < 0.95
        # Below md 0.9375 the 0.95 bar is out of reach at any cover
        # score — the ceiling CV's publisher/page-less search results
        # actually live under.
        cv_shaped = replace(_candidate(), metadata_score=0.9125, cover_score=1.0)
        assert final_score(cv_shaped, hash_used=True) < 0.95
        # Un-hashed, the same metadata score is the score.
        assert final_score(cv_shaped, hash_used=False) == 0.9125

    def test_same_candidate_auto_writes_unmeasured_and_prompts_measured(self) -> None:
        """
        One perfect-metadata candidate, two outcomes, decided by its cover.

        Without a local cover to hash against (thumbnail library, PDF
        with no readable page, cover fetch failure) the candidate keeps
        md=1.0 and auto-writes. With a mediocre measured cover it lands
        at 0.90 and prompts, on identical metadata.
        """
        matcher = OnlineMatcher()
        # A perfect match plus a near-tie: the gap stays under the
        # disambiguation margin, which is what invokes hashing at all.
        candidates = [
            _candidate(issue_id=1, volume_id=10, cover_url=_COVER_URL),
            _candidate(issue_id=2, volume_id=20, page_count=22, cover_url=_COVER_URL),
        ]
        settings = _settings(auto_threshold=0.95, match=MatchMode.EAGER)

        unmeasured = matcher.rank(_profile(), candidates)
        assert unmeasured[0].score == pytest.approx(1.0)
        assert (
            matcher.resolve(unmeasured, settings, "metron").kind
            is ResolutionKind.AUTO_WRITE
        )

        measured = matcher.rank(
            _profile(),
            candidates,
            local_hash_provider=lambda: _LOCAL_HASH,
            candidate_hash_fetcher=lambda _url: _HALF_MATCH_HASH,
            threshold=0.95,
        )
        assert measured[0].cover_score == pytest.approx(0.5)
        assert measured[0].score == pytest.approx(0.9)
        assert (
            matcher.resolve(measured, settings, "metron").kind is ResolutionKind.PROMPT
        )
