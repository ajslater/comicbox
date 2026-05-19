"""
Per-signal scoring functions for the matcher.

Each `s_*` returns a value in `[0, 1]`. Missing inputs are treated as
"uncertain, partial credit" rather than "definitely wrong" so a
candidate isn't penalised for the *comic* being thin on metadata.

The cover-hash signal lives in `cover_hash.py` (M4); this module only
covers metadata signals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from comicbox.formats.base.online.profile import Candidate, ComicProfile

import re
from types import MappingProxyType
from typing import Final

# Year-signal anchors. Original calibration values for diff in {0, 1, 2};
# beyond diff=2 we linearly decay to 0.0 at `_YEAR_DECAY_ZERO` (Phase F).
# See `s_year` docstring for the rationale.
_YEAR_ANCHORS: Final[MappingProxyType[int, float]] = MappingProxyType(
    {0: 1.0, 1: 0.7, 2: 0.4}
)
_YEAR_DECAY_ZERO: Final[int] = 7

_VOLUME_SUFFIX_RE = re.compile(
    r"\s*(?:\(\s*)?(?:vol(?:ume|\.)?)\s*\d+\s*\)?", re.IGNORECASE
)
_PUBLISHER_NOISE_RE = re.compile(
    r"\b(?:inc|incorporated|comics?|publishing|press|llc|ltd|publications?)\b\.?",
    re.IGNORECASE,
)
_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_series(name: str) -> str:
    """Lowercase, strip volume suffixes, collapse non-alphanumeric runs."""
    s = name.lower()
    s = _VOLUME_SUFFIX_RE.sub(" ", s)
    s = _NON_ALPHANUM_RE.sub(" ", s)
    return " ".join(s.split())


# Backward-compat alias for the previously-private helper. Other modules
# in `comicbox.formats.base.online` import the public `normalize_series`; keep the
# old name resolving until those migrations land.
_normalize_series = normalize_series


def _normalize_publisher(name: str) -> str:
    """Lowercase, strip 'Inc' / 'Comics' suffixes, collapse whitespace."""
    s = name.lower()
    s = _PUBLISHER_NOISE_RE.sub(" ", s)
    s = _NON_ALPHANUM_RE.sub(" ", s)
    return " ".join(s.split())


def s_series(profile: ComicProfile, candidate: Candidate) -> float:
    """Series-name similarity via rapidfuzz `WRatio`, normalized."""
    if not profile.series or not candidate.summary.series:
        return 0.0
    a = _normalize_series(profile.series)
    b = _normalize_series(candidate.summary.series)
    if not a or not b:
        return 0.0
    return float(fuzz.WRatio(a, b)) / 100.0


def _candidate_issue_int(candidate: Candidate) -> int | None:
    """Parse the candidate's issue as a non-negative int; None if non-numeric."""
    if not candidate.summary.issue:
        return None
    cand_s = candidate.summary.issue.strip()
    if not cand_s.isdigit():
        return None
    return int(cand_s.lstrip("0") or "0")


def s_issue(profile: ComicProfile, candidate: Candidate) -> float:
    """Issue number match. Integer-equal first; fall back to string-equal."""
    if profile.issue_int is not None:
        cand_int = _candidate_issue_int(candidate)
        if cand_int is not None:
            return 1.0 if cand_int == profile.issue_int else 0.0

    if not profile.issue or not candidate.summary.issue:
        return 0.5

    return (
        1.0
        if profile.issue.strip().lower() == candidate.summary.issue.strip().lower()
        else 0.0
    )


def s_year(profile: ComicProfile, candidate: Candidate) -> float:
    """
    Year match with smooth decay beyond the original 1.0/0.7/0.4 anchors.

    - 1.0 on exact match
    - 0.7 at ±1 year
    - 0.4 at ±2 years
    - Linear decay from 0.4 (diff=2) to 0.0 (diff=7) — Phase F
    - 0.0 for diff ≥ 7

    Missing-data handling distinguishes two cases:
      - both missing: 0.5 (weak agnostic prior — we have no signal)
      - asymmetric (one side has year, other doesn't): 0.3
        (the previous 0.6 over-credited unknown candidates and let
        wrong-volume picks coast through the auto-write band when CV's
        BasicIssue lacked a cover_date)

    Phase F (2026-05-14) replaced the original cliff (0.0 for any
    diff ≥ 3) with linear decay. The cliff treated modern reissues of
    older series as having no year signal at all — fine for the
    common case where year discriminates between volumes, but bad
    when the right candidate IS the same series at a different year
    (e.g. The Boys 2009 fixture's expected vol was at year=2006, gap
    of 3 years). Smooth decay gives the older candidate ~75% of the
    one-year-off signal, enough to compete with cover-hash signal
    when present. Beyond 7 years, the score still hits zero — the
    long tail of 20+ year reissues (Conan 1973 vs 2025) shouldn't
    benefit from year signal.

    See `tasks/online-tagging/calibration-notes/2026-05-14-bigmedia-247.md`
    for the failure-mode analysis that motivated this change.
    """
    if profile.year is None and candidate.summary.year is None:
        return 0.5
    if profile.year is None or candidate.summary.year is None:
        return 0.3
    diff = abs(profile.year - candidate.summary.year)
    if diff in _YEAR_ANCHORS:
        return _YEAR_ANCHORS[diff]
    # Linear decay from the diff=2 anchor (0.4) to 0.0 at `_YEAR_DECAY_ZERO`.
    # `max` clamps the long tail (diff ≥ _YEAR_DECAY_ZERO → 0.0).
    decay_span = _YEAR_DECAY_ZERO - 2
    return max(0.0, _YEAR_ANCHORS[2] * (_YEAR_DECAY_ZERO - diff) / decay_span)


def s_publisher(profile: ComicProfile, candidate: Candidate) -> float:
    """Score publisher equality after normalization."""
    if not profile.publisher or not candidate.summary.publisher:
        return 0.5
    return (
        1.0
        if _normalize_publisher(profile.publisher)
        == _normalize_publisher(candidate.summary.publisher)
        else 0.0
    )


def s_pages(profile: ComicProfile, candidate: Candidate) -> float:
    """Page-count match: 1 if equal, 0.7 within 10%, 0.3 within 25%, else 0."""
    if profile.page_count is None or candidate.summary.page_count is None:
        return 0.6
    if profile.page_count == candidate.summary.page_count:
        return 1.0
    if profile.page_count == 0:
        return 0.0
    ratio = abs(profile.page_count - candidate.summary.page_count) / profile.page_count
    if ratio <= 0.10:  # noqa: PLR2004
        return 0.7
    if ratio <= 0.25:  # noqa: PLR2004
        return 0.3
    return 0.0
