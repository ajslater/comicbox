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
    from comicbox.online.profile import Candidate, ComicProfile

import re

_VOLUME_SUFFIX_RE = re.compile(
    r"\s*(?:\(\s*)?(?:vol(?:ume|\.)?)\s*\d+\s*\)?", re.IGNORECASE
)
_PUBLISHER_NOISE_RE = re.compile(
    r"\b(?:inc|incorporated|comics?|publishing|press|llc|ltd|publications?)\b\.?",
    re.IGNORECASE,
)
_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_series(name: str) -> str:
    """Lowercase, strip volume suffixes, collapse non-alphanumeric runs."""
    s = name.lower()
    s = _VOLUME_SUFFIX_RE.sub(" ", s)
    s = _NON_ALPHANUM_RE.sub(" ", s)
    return " ".join(s.split())


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


def s_issue(profile: ComicProfile, candidate: Candidate) -> float:
    """Issue number match. Integer-equal first; fall back to string-equal."""
    if profile.issue_int is not None and candidate.summary.issue:
        cand_int = None
        cand_s = candidate.summary.issue.strip()
        if cand_s.isdigit():
            cand_int = int(cand_s.lstrip("0") or "0")
        if cand_int is not None:
            return 1.0 if cand_int == profile.issue_int else 0.0

    if not profile.issue and not candidate.summary.issue:
        return 0.5
    if not profile.issue or not candidate.summary.issue:
        return 0.5

    return (
        1.0
        if profile.issue.strip().lower() == candidate.summary.issue.strip().lower()
        else 0.0
    )


def s_year(profile: ComicProfile, candidate: Candidate) -> float:
    """Year match: 1 if equal, 0.7 if ±1, 0.4 if ±2, 0 otherwise. 0.6 if missing."""
    if profile.year is None or candidate.summary.year is None:
        return 0.6
    diff = abs(profile.year - candidate.summary.year)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.7
    return 0.4 if diff == 2 else 0.0  # noqa: PLR2004


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
