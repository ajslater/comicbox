"""
Test doubles for ``OnlineSession``.

Shared by ``test_online_session``, which checks construction and settings,
and ``test_online_session_lookup``, which runs lookups through a box.
"""

from __future__ import annotations

from comicbox.online_session import OnlinePrompt, PromptResponse


class SkipHandler:
    """Answers every prompt with skip and keeps what it was asked."""

    def __init__(self) -> None:
        """Start with no prompts seen."""
        self.prompts: list[OnlinePrompt] = []

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        self.prompts.append(prompt)
        return PromptResponse(action="skip")
