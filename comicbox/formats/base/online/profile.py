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
from typing import Any, Final

from glom import glom


@dataclass(frozen=True, slots=True)
class ComicProfile:
    """Comic-side inputs for the matcher."""

    series: str | None = None
    issue: str | None = None
    issue_int: int | None = None
    year: int | None = None
    publisher: str | None = None
    page_count: int | None = None
    # Series volume ordinal (e.g. "Spider-Man Vol. 2 #1" → 2). When set,
    # used as a soft search filter for sources that support it (Metron's
    # `series_volume`); CV's API has no ordinal-volume filter.
    volume: int | None = None


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
    # The parent container's id — CV's `volume.id`, Metron's `series.id`.
    # Two issues sharing a volume_id are siblings in the same series run;
    # this is what calibration uses to distinguish "variant cover of the
    # same issue" (same volume_id) from "wrong-series collision" (different
    # volume_ids that happen to share a name like "Watchmen"). Sources set
    # this when constructing the candidate; left as None for sources that
    # don't expose it.
    volume_id: int | None = None


_INT_RE = re.compile(r"^\d+$")
_LEADING_DIGITS_RE = re.compile(r"^(\d+)(.*)$")


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


def strip_issue_leading_zeros(raw: str | None) -> str | None:
    """
    Strip leading zeros from an issue number string, preserving any suffix.

    Used when building API search params: comicvine, metron, etc. expect
    `7` not `007`. Variant suffixes (`a`, `.5`) survive unchanged.

    Examples:
        "007" → "7"
        "001a" → "1a"
        "0" → "0"
        "1.5" → "1.5"
        "Special" → "Special"
        None → None

    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return s
    m = _LEADING_DIGITS_RE.match(s)
    if not m:
        return s
    digits, rest = m.groups()
    stripped = digits.lstrip("0") or "0"
    return stripped + rest


def parse_year(raw: Any) -> int | None:
    """Pull a 4-digit year out of a date-ish input."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r"\b(\d{4})\b", s)
    return int(m.group(1)) if m else None


def _resolve_volume(md: dict) -> int | None:
    """
    Extract `comicbox.volume.number` as an int, defensively.

    Rejects 4-digit year-shaped values (1900-2100). The
    [ComicInfo.xml convention](https://anansi-project.github.io/docs/comicinfo/documentation#volume)
    of using the year-of-first-issue as the volume number is widespread
    (comictagger writes it that way), but Metron's `series_volume`
    filter expects an ordinal (1, 2, 3 — "Vol. N of M"). Sending the
    year as `series_volume` matches no issues and wastes API budget on
    the drop-volume retry.

    A real volume "Vol. 2019 of 9999" doesn't exist in the wild —
    real ordinal volumes are well under 50 in practice. Treating
    1900-2100 as "year masquerading as volume" is safe and matches the
    failure mode we actually see.
    """
    raw = glom(md, "comicbox.volume.number", default=None)
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if 1900 <= v <= 2100:  # noqa: PLR2004 — year range, not a magic threshold
        return None
    return v


_SIMPLE_PROFILE_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("series", "comicbox.series.name"),
    ("issue", "comicbox.issue.name"),
    ("publisher", "comicbox.publisher.name"),
    ("page_count", "comicbox.page_count"),
)


def accumulate_profile_fields(fields: dict[str, Any], md: dict) -> None:
    """First-wins accumulation of profile fields across normalized sources."""
    for field_name, path in _SIMPLE_PROFILE_PATHS:
        if field_name not in fields and (v := glom(md, path, default=None)):
            fields[field_name] = v
    if "year" not in fields:
        raw_year = glom(md, "comicbox.date.year", default=None) or glom(
            md, "comicbox.date.cover_date", default=None
        )
        if (parsed := parse_year(raw_year)) is not None:
            fields["year"] = parsed
    if "volume" not in fields and (v := _resolve_volume(md)) is not None:
        fields["volume"] = v
