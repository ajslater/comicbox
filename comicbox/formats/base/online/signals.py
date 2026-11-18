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

from comicbox.series_name import normalize_series

if TYPE_CHECKING:
    from comicbox.formats.base.online.profile import Candidate, ComicProfile

import re
from itertools import pairwise
from types import MappingProxyType
from typing import Final

# Year-signal anchors. Original calibration values for diff in {0, 1, 2};
# beyond diff=2 we linearly decay to 0.0 at `_YEAR_DECAY_ZERO` (Phase F).
# See `s_year` docstring for the rationale.
_YEAR_ANCHORS: Final[MappingProxyType[int, float]] = MappingProxyType(
    {0: 1.0, 1: 0.7, 2: 0.4}
)
_YEAR_DECAY_ZERO: Final[int] = 7

_PUBLISHER_NOISE_RE = re.compile(
    r"\b(?:inc|incorporated|comics?|publishing|press|llc|ltd|publications?)\b\.?",
    re.IGNORECASE,
)
_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_publisher(name: str) -> str:
    """Lowercase, strip 'Inc' / 'Comics' suffixes, collapse whitespace."""
    s = name.lower()
    s = _PUBLISHER_NOISE_RE.sub(" ", s)
    s = _NON_ALPHANUM_RE.sub(" ", s)
    return " ".join(s.split())


# Words too common in series names to show two names are the same series:
# darkseid's `remove_articles` list, which metron-tagger's cover search
# uses (metron-tagger#294), plus "vs". "it's" is absent because the
# apostrophe has already joined it to "its".
_SERIES_STOP_WORDS: Final = frozenset(
    {
        "a",
        "am",
        "an",
        "and",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "if",
        "is",
        "issue",
        "it",
        "its",
        "itself",
        "of",
        "or",
        "so",
        "the",
        "vs",
        "with",
    }
)
# A hyphen, slash or apostrophe inside a word joins its parts, so
# "Spider-Man" is one word and doesn't match "Iron Man" on "man".
_SERIES_WORD_JOINERS_RE: Final = re.compile(r"(?<=\w)[-/'\u2019](?=\w)")


def series_words(name: str) -> frozenset[str]:
    """
    Return the distinctive words of a series name, for telling names apart.

    Words are normalized as `normalize_series` normalizes a name, after a
    hyphen, slash or apostrophe inside a word joins it. Stop words are
    dropped. Each pair of neighbouring words is also included joined, so
    Metron's "Batman / Superman" (a spaced slash, two words) and a
    filename's "Batman-Superman" (one word) share "batmansuperman".
    """
    words = [
        word
        for word in normalize_series(_SERIES_WORD_JOINERS_RE.sub("", name)).split()
        if word not in _SERIES_STOP_WORDS
    ]
    return frozenset((*words, *(a + b for a, b in pairwise(words))))


def series_words_agree(a: str | None, b: str | None) -> bool:
    """
    Whether two series names share a distinctive word.

    A coarse check, by design: a filename often names only part of a
    series ("Star Wars" for *Star Wars: The Book of Boba Fett*), so this
    asks only whether the names could be the same series, not how alike
    they are. It is what stops a close cover from another series with the
    same issue number being taken as a match.
    """
    return bool(a and b and series_words(a) & series_words(b))


def s_series(profile: ComicProfile, candidate: Candidate) -> float:
    """
    Series-name similarity via rapidfuzz `WRatio`, normalized.

    Scores the best of the candidate's primary series name and its
    alternative names (`summary.alt_series` — ComicVine volume aliases),
    so a comic filed under a localized or variant title still matches
    its canonical volume.
    """
    if not profile.series or not (a := normalize_series(profile.series)):
        return 0.0
    summary = candidate.summary
    return max(
        (
            float(fuzz.WRatio(a, b)) / 100.0
            for name in (summary.series, *summary.alt_series)
            if name and (b := normalize_series(name))
        ),
        default=0.0,
    )


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
