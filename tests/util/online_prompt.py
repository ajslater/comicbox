"""
Builders for the CLI selector's test doubles.

Shared by ``test_online_prompt``, which renders and parses replies, and
``test_online_prompt_loops``, which drives the submenus with scripted
reply sequences.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING, cast

from comicbox.config import get_config
from comicbox.formats.base.online.profile import Candidate, CandidateSummary
from comicbox.formats.base.online.selector import SelectorContext

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings


def make_summary(
    *,
    series: str = "Foo Comics",
    issue: str = "5",
    year: int | None = 2020,
    publisher: str | None = "Quality Comics",
    page_count: int | None = 24,
) -> CandidateSummary:
    return CandidateSummary(
        series=series,
        issue=issue,
        year=year,
        publisher=publisher,
        page_count=page_count,
        cover_url=None,
        variant_label=None,
    )


def make_candidate(
    issue_id: int = 101,
    *,
    url: str = "",
    score: float = 0.91,
    cover_score: float | None = None,
    **summary_kwargs,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=make_summary(**summary_kwargs),
        score=score,
        cover_score=cover_score,
        url=url,
    )


class ScriptedPrompt:
    """Stand-in for `_prompt_line` replaying a fixed reply sequence."""

    def __init__(self, *replies: str | None) -> None:
        """Queue the replies the prompt will hand back, in order."""
        self.replies: list[str | None] = list(replies)
        self.messages: list[str] = []

    def __call__(self, message: str) -> str | None:
        self.messages.append(message)
        if not self.replies:
            reason = f"prompt asked past the end of the script: {message!r}"
            raise AssertionError(reason)
        return self.replies.pop(0)


def make_settings(loglevel: str | int = "INFO") -> ComicboxSettings:
    """Real settings with only the loglevel pinned — terse's one input."""
    return get_config(
        Namespace(comicbox=Namespace(general=Namespace(loglevel=loglevel)))
    )


def make_context(
    *,
    file_path: object = None,
    source: str = "metron",
    settings: object = None,
) -> SelectorContext:
    return SelectorContext(
        file_path=cast("None", file_path),
        source=source,
        settings=cast("ComicboxSettings", settings) if settings else make_settings(),
        triggered_hashing=False,
    )
