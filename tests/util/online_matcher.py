"""
Builders for the online matcher's test doubles.

Shared by ``test_online_matcher`` and ``test_online_matcher_resolution``,
which score candidates and resolve them respectively but describe the same
comic to do it.
"""

from __future__ import annotations

from typing import Any

from comicbox.config.online.settings import MatchMode
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)


# Back-compat alias: legacy tests still spell the resolution policy as
# ``Policy.ALWAYS_PROMPT / STRICT / NORMAL / EAGER``. Provide a shim that
# maps each spelling to its v4 ``MatchMode`` so existing test bodies need
# no changes beyond the import.
class Policy:
    """Shim mapping legacy ``Policy.*`` names to v4 ``MatchMode`` members."""

    ALWAYS_PROMPT = MatchMode.ASK
    STRICT = MatchMode.CAREFUL
    NORMAL = MatchMode.AUTO
    EAGER = MatchMode.EAGER


def make_candidate(
    *,
    issue_id: int = 1,
    series: str = "Foo Comics",
    issue: str = "5",
    year: int | None = 2020,
    publisher: str | None = "Quality Comics",
    page_count: int | None = 24,
    volume_id: int | None = None,
    alt_series: tuple[str, ...] = (),
) -> Candidate:
    """Build a candidate that matches ``make_profile()`` unless told otherwise."""
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series=series,
            issue=issue,
            year=year,
            publisher=publisher,
            page_count=page_count,
            cover_url=None,
            variant_label=None,
            alt_series=alt_series,
        ),
        volume_id=volume_id,
    )


def make_profile(**overrides: Any) -> ComicProfile:
    """Build the comic the candidates are matched against."""
    base: dict[str, Any] = {
        "series": "Foo Comics",
        "issue": "5",
        "issue_int": 5,
        "year": 2020,
        "publisher": "Quality Comics",
        "page_count": 24,
    }
    base.update(overrides)
    return ComicProfile(**base)
