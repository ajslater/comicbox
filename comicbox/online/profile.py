"""
ComicProfile / Candidate types and helpers.

`ComicProfile` is the input the matcher reads to score candidates against
the comic at hand. It's built once per comic from the normalized
non-online source metadata so we don't depend on what the online lookup
itself produced.

`Candidate` and `CandidateSummary` are the matcher output unit — one per
search hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ComicProfile:
    """Comic-side inputs for the matcher."""

    series: str | None = None
    issue: str | None = None
    issue_int: int | None = None
    year: int | None = None
    publisher: str | None = None
    page_count: int | None = None


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    """Display fields shown in the prompt UX."""

    series: str
    issue: str
    year: int | None
    publisher: str | None
    page_count: int | None
    cover_url: str | None
    variant_label: str | None


@dataclass(frozen=True, slots=True)
class Candidate:
    """One search result, post-ranking."""

    source: str
    issue_id: int
    summary: CandidateSummary
    raw: dict[str, Any] = field(default_factory=dict)
    metadata_score: float = 0.0
    cover_score: float | None = None
    score: float = 0.0
    url: str = ""
    precomputed_cover_hash: str | None = None


_INT_RE = re.compile(r"^\d+$")


def parse_issue_int(raw: Any) -> int | None:
    """
    Return the integer form of an issue number when parseable.

    Strips leading zeros (`001` → `1`); returns None for non-numeric forms
    like `1a`, `1.5`, `0a`, `Special`, etc.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or not _INT_RE.match(s):
        return None
    return int(s)


def parse_year(raw: Any) -> int | None:
    """Pull a 4-digit year out of a date-ish input."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r"\b(\d{4})\b", s)
    return int(m.group(1)) if m else None
