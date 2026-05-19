"""
Shared event types for read / write / online workflows.

One ``on_event`` callback shape across the three public bulk entry points
(``iter_process_files``, ``bulk_write``, ``OnlineSession.tag_many``) so a
caller — typically Codex — can wire a single handler.

Handlers run on the orchestrator thread that drains worker results. They
must be thread-safe and should return quickly; expensive work belongs in a
queue the handler dispatches to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class Event:
    """
    Base for all workflow events.

    Subclasses are concrete frozen dataclasses keyed by the ``kind`` literal
    on the subclass — callers can ``match`` on type or on ``kind``.
    """

    kind: str
    path: Path | None = None
    index: int | None = None
    total: int | None = None


# ---------------------------------------------------------------------------
# Read workflow
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BatchStarted(Event):
    """Fired once before the first file is submitted."""

    kind: Literal["batch_started"] = "batch_started"


@dataclass(frozen=True, slots=True)
class FileShortCircuited(Event):
    """
    Worker decided the embedded metadata had not changed and skipped parse.

    ``reason="mtime_unchanged"`` — embedded mtime <= caller's ``old_mtime``.
    ``reason="filtered"``        — caller passed ``full_metadata=False`` so
                                   the worker only collected envelope fields.
    """

    reason: Literal["mtime_unchanged", "filtered"] = "mtime_unchanged"
    kind: Literal["file_short_circuited"] = "file_short_circuited"


@dataclass(frozen=True, slots=True)
class FileParsed(Event):
    """Worker fully parsed embedded metadata."""

    kind: Literal["file_parsed"] = "file_parsed"


@dataclass(frozen=True, slots=True)
class FileError(Event):
    """Worker raised an exception. ``error`` is the str(exception)."""

    error: str = ""
    kind: Literal["file_error"] = "file_error"


@dataclass(frozen=True, slots=True)
class BatchFinished(Event):
    """
    Fired once after every file has been delivered.

    ``parsed`` / ``short_circuited`` / ``errored`` carry per-outcome counts
    so callers can render an end-of-batch summary without re-walking the
    result stream.
    """

    parsed: int = 0
    short_circuited: int = 0
    errored: int = 0
    kind: Literal["batch_finished"] = "batch_finished"


# Convenience union for read events specifically.
ReadEvent: TypeAlias = (
    BatchStarted | FileShortCircuited | FileParsed | FileError | BatchFinished
)


# ---------------------------------------------------------------------------
# Online workflow
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SearchStarted(Event):
    """Worker is about to query an online source for this file."""

    source: str = ""
    kind: Literal["search_started"] = "search_started"


@dataclass(frozen=True, slots=True)
class SearchCompleted(Event):
    """Online source returned candidate list."""

    source: str = ""
    n_candidates: int = 0
    top_score: float | None = None
    kind: Literal["search_completed"] = "search_completed"


@dataclass(frozen=True, slots=True)
class AutoWritten(Event):
    """Matcher accepted a candidate without prompting."""

    source: str = ""
    candidate_summary: str = ""
    kind: Literal["auto_written"] = "auto_written"


@dataclass(frozen=True, slots=True)
class PromptQueued(Event):
    """Matcher needs human input; prompt dispatched to PromptHandler."""

    source: str = ""
    prompt_id: str = ""
    n_candidates: int = 0
    kind: Literal["prompt_queued"] = "prompt_queued"


@dataclass(frozen=True, slots=True)
class PromptResolved(Event):
    """PromptHandler returned a decision."""

    source: str = ""
    prompt_id: str = ""
    action: str = ""
    kind: Literal["prompt_resolved"] = "prompt_resolved"


@dataclass(frozen=True, slots=True)
class Skipped(Event):
    """Matcher declined to write metadata for this file."""

    source: str = ""
    reason: str = ""
    kind: Literal["skipped"] = "skipped"


@dataclass(frozen=True, slots=True)
class NoMatch(Event):
    """No candidate cleared min_confidence."""

    source: str = ""
    kind: Literal["no_match"] = "no_match"


@dataclass(frozen=True, slots=True)
class RateLimited(Event):
    """
    Source signaled a rate-limit hit.

    ``retry_after_seconds`` is the server hint when available; otherwise
    the per-source retry-schedule's next sleep.
    """

    source: str = ""
    retry_after_seconds: float | None = None
    kind: Literal["rate_limited"] = "rate_limited"


@dataclass(frozen=True, slots=True)
class FileFinished(Event):
    """Per-file online tagging completed (success, skip, no-match, or error)."""

    outcome: str = ""
    kind: Literal["file_finished"] = "file_finished"


# Convenience union for online events.
OnlineEvent: TypeAlias = (
    BatchStarted
    | SearchStarted
    | SearchCompleted
    | AutoWritten
    | PromptQueued
    | PromptResolved
    | Skipped
    | NoMatch
    | RateLimited
    | FileFinished
    | FileError
    | BatchFinished
)


# Public handler shape exposed by every bulk workflow.
EventHandler: TypeAlias = Callable[[Event], None]
