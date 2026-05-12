"""
Pre-call series-name fuzzy filter for online sources.

Each source's volume/series discovery step returns up to N hits for a
free-text series query. CV's full-text search will return "Lois Lane: A
Celebration" and "Lois Lane and Friends" alongside the canonical "Lois
Lane (2019)" — and the matcher's `s_series` signal would score the
non-matches near zero anyway. Issuing the per-volume `list_issues` API
call for those non-matches is wasted budget under CV's 200/hr cap.

This module provides the pre-call filter both sources consult before
deciding to spend an API call on a discovered volume. The same
`normalize_series` from `signals.py` is reused so a candidate that
passes the filter scores predictably under `s_series` downstream.

**Why `fuzz.ratio` and not `fuzz.WRatio`** (which `s_series` uses):
WRatio applies a partial-match boost that lifts any substring overlap
to 90+, including "Lois Lane" vs "Adventures of Lois Lane and Friends"
(both score 90). That's fine for *scoring* — the matcher's downstream
signals can still rank candidates — but useless for *filtering*, where
we need to drop substring-overlapping-but-different volumes before
issuing an API call for them. Plain `ratio` (Levenshtein) gives:

    Lois Lane vs Lois Lane (1986)              → 78
    Lois Lane vs Watchmen (1986)               → variant year tail OK
    Lois Lane vs Watchmen Annotated            → 62
    Lois Lane vs Adventures of Lois Lane ...   → 41

A natural threshold around 0.70 separates "same series, possibly with a
year/volume suffix" (keep) from "different series that happens to share
words" (drop). The pre-filter is intentionally STRICTER than the
matcher's `s_series`; the matcher gets to be permissive because it sees
the full candidate. The pre-filter has to decide before any API call
goes out.

Driven by the `APIBudget` resolved per-source. See
`tasks/online-tagging/06-api-budget-spec.md` for the threshold rationale
(Phase B picks the real numbers; Phase A ships with the lever dormant).
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Final

from rapidfuzz import fuzz

from comicbox.config.settings import APIBudget
from comicbox.online.signals import normalize_series

# CV (and to a lesser extent Metron) annotate volume names with the
# series's publication year in parens: "Lois Lane (1986)", "Conan (2004)",
# "Watchmen (1986-1990)". For pre-filter purposes that's structural
# noise — the profile only carries the bare series name. Without
# stripping, "Conan" vs "Conan (2004)" scores 67% under plain ratio,
# which is below the 0.7 threshold and would drop the right answer.
#
# We strip ONLY pure year / year-range parentheticals. Anything else in
# parens (e.g. "(Annotated)", "(2008 Reprint)", "(Special Edition)") is
# preserved — those legitimately denote different volumes and we WANT
# the ratio to drop accordingly. Hyphen / en-dash both accepted for the
# range separator since CV uses both.
# En-dash (U+2013) handled as well as hyphen-minus since CV occasionally
# uses the typographic variant for year ranges. The literal en-dash in
# the character class is intentional — RUF001's ambiguity warning is
# the false positive here.
_YEAR_PAREN_RE = re.compile(
    r"\s*\(\s*\d{4}(?:\s*[-–]\s*\d{4})?\s*\)"  # noqa: RUF001 — intentional
)


def _strip_year_parens(s: str) -> str:
    """Drop `(YYYY)` / `(YYYY-YYYY)` annotations; preserve other parens."""
    return _YEAR_PAREN_RE.sub("", s).strip()


# Per-budget similarity threshold. A volume's name must score AT LEAST
# this against the comic's `profile.series` to survive the filter and
# get its issue-list call. Threshold 0.0 = filter is a no-op.
#
# Values are Phase B-validated against the spring-2026 339-fixture
# calibration set. See `tasks/online-tagging/calibration-notes/` for the
# experiment data behind each number.
_THRESHOLDS: Final[MappingProxyType[APIBudget, float]] = MappingProxyType(
    {
        # EXHAUSTIVE never filters — semantically off. Spend API budget
        # freely; recover the very long tail of edge cases.
        APIBudget.EXHAUSTIVE: 0.0,
        # BALANCED at 0.4 (Phase B-validated): zero outcome changes vs
        # 0.0 across the full fixture set, 18% fewer API calls. Strictly
        # better than the previous "today's behavior" of 0.0.
        APIBudget.BALANCED: 0.4,
        # FAST at 0.7 (Phase B-validated): 100% accuracy on labeled
        # fixtures, 60.5% fewer API calls than balanced-at-0. Catches
        # the "Moebius Library vs Adventures of Basil & Moebius"-style
        # substring false positives.
        APIBudget.FAST: 0.7,
    }
)


def threshold_for(budget: APIBudget) -> float:
    """Return the per-budget filter threshold in `[0, 1]`."""
    return _THRESHOLDS.get(budget, 0.0)


def should_keep_volume_name(
    profile_series: str | None,
    volume_name: str | None,
    threshold: float,
) -> bool:
    """
    Decide whether a discovered volume is worth a per-volume issue lookup.

    Returns True (keep, spend the API call) when either:

    - `threshold <= 0` — the filter is configured as no-op for the
      resolved API budget. This is `BALANCED` until Phase B says
      otherwise.
    - `profile_series` is missing — we have no comparison anchor; never
      drop on missing data (would risk false-negatives for
      tagged-without-series fixtures).
    - `volume_name` is missing — likewise, can't compare; keep.
    - The rapidfuzz `ratio` similarity between the two normalized
      names is `>= threshold * 100`. Same normalization as
      `s_series` (so naming conventions agree), different primitive
      (so we filter substring noise the matcher would still score
      high). See module docstring for rationale.

    Returns False (skip, save the call) otherwise. The caller is
    expected to log a debug-level reason when this happens so
    calibration runs can audit pre-filter false-negatives.
    """
    if threshold <= 0.0:
        return True
    if not profile_series or not volume_name:
        return True
    a = normalize_series(_strip_year_parens(profile_series))
    b = normalize_series(_strip_year_parens(volume_name))
    if not a or not b:
        return True
    return float(fuzz.ratio(a, b)) >= threshold * 100.0
