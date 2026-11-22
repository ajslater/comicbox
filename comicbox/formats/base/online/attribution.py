"""
The credit an online source's terms require wherever its data is shown.

VerseDB asks for a linked "Data from VerseDB" credit on any page or screen
that shows its data, near the data. comicbox prints it under VerseDB's
candidates in the CLI prompt; a frontend such as Codex looks it up by the
source name that `OnlinePrompt.source` and `Candidate.source` already carry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceAttribution:
    """A credit and the link it must carry."""

    text: str
    url: str


def source_attribution(name: str) -> SourceAttribution | None:
    """Return the credit ``name``'s terms require, or None when they ask for none."""
    from comicbox.formats import FORMAT_REGISTRATIONS

    for registration in FORMAT_REGISTRATIONS.values():
        info = registration.cli_info
        if info is not None and info.short_name == name and info.attribution:
            return SourceAttribution(text=info.attribution, url=info.website)
    return None
