"""
End-of-run outcome counters for online tagging.

Tracks how many comics fell into each match-resolution bucket across a
run so the runner can print a summary like:

  Online tagging summary:
    16 auto-written
     2 prompted (chose 1, declined 1)
     3 skipped
     1 no-match

Process-wide singleton; reset at the start of each `Runner.run()`.
Thread-safe so `-j N` parallel batches contribute correctly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _Counts:
    auto_write: int = 0
    prompt_accepted: int = 0
    prompt_declined: int = 0
    skip: int = 0
    no_match: int = 0
    # Direct id-fetch path (`--id <db>:<n>`); not technically a resolution
    # outcome but worth distinguishing in the summary.
    explicit_id: int = 0


class _OutcomeStats:
    """Process-wide thread-safe outcome counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = _Counts()
        self._per_source: dict[str, _Counts] = {}

    def reset(self) -> None:
        """Clear all counters (called at the start of each Runner.run())."""
        with self._lock:
            self._counts = _Counts()
            self._per_source = {}

    def _bucket_for(self, source_name: str) -> _Counts:
        """Get-or-create the per-source bucket. Caller must hold `_lock`."""
        bucket = self._per_source.get(source_name)
        if bucket is None:
            bucket = _Counts()
            self._per_source[source_name] = bucket
        return bucket

    def record_auto_write(self, source_name: str) -> None:
        """Record an auto-written candidate (no prompt)."""
        with self._lock:
            self._counts.auto_write += 1
            self._bucket_for(source_name).auto_write += 1

    def record_prompt_accepted(self, source_name: str) -> None:
        """Record a candidate picked from a user prompt."""
        with self._lock:
            self._counts.prompt_accepted += 1
            self._bucket_for(source_name).prompt_accepted += 1

    def record_prompt_declined(self, source_name: str) -> None:
        """Record a user declining the prompt (no candidate selected)."""
        with self._lock:
            self._counts.prompt_declined += 1
            self._bucket_for(source_name).prompt_declined += 1

    def record_skip(self, source_name: str) -> None:
        """Record a SKIP (matcher declined under `--unattended`)."""
        with self._lock:
            self._counts.skip += 1
            self._bucket_for(source_name).skip += 1

    def record_no_match(self, source_name: str) -> None:
        """Record a NO_MATCH (no candidate cleared `min_confidence`)."""
        with self._lock:
            self._counts.no_match += 1
            self._bucket_for(source_name).no_match += 1

    def record_explicit_id(self, source_name: str) -> None:
        """Record a direct `--id <db>:<n>` fetch (bypasses resolution)."""
        with self._lock:
            self._counts.explicit_id += 1
            self._bucket_for(source_name).explicit_id += 1

    def has_any_activity(self) -> bool:
        """Return True if any outcome was recorded since last reset."""
        with self._lock:
            return _has_any(self._counts)

    def summary_lines(self) -> list[str]:
        """Format the end-of-run summary as a list of log lines."""
        with self._lock:
            if not _has_any(self._counts):
                return []
            counts_snapshot = _Counts(**self._counts.__dict__)
            per_source_snapshot = {
                k: _Counts(**v.__dict__) for k, v in self._per_source.items()
            }
        return _format_summary(counts_snapshot, per_source_snapshot)


def _has_any(c: _Counts) -> bool:
    return any(
        (
            c.auto_write,
            c.prompt_accepted,
            c.prompt_declined,
            c.skip,
            c.no_match,
            c.explicit_id,
        )
    )


def _format_summary(c: _Counts, per_source: dict[str, _Counts]) -> list[str]:
    total = (
        c.auto_write
        + c.prompt_accepted
        + c.prompt_declined
        + c.skip
        + c.no_match
        + c.explicit_id
    )
    lines = [f"Online tagging summary ({total} comic-sources):"]
    if c.auto_write:
        lines.append(f"  {c.auto_write:>4} auto-written")
    if c.explicit_id:
        lines.append(f"  {c.explicit_id:>4} fetched by --id")
    if c.prompt_accepted or c.prompt_declined:
        lines.append(
            f"  {c.prompt_accepted + c.prompt_declined:>4} prompted "
            f"(chose {c.prompt_accepted}, declined {c.prompt_declined})"
        )
    if c.skip:
        lines.append(f"  {c.skip:>4} skipped (matcher declined)")
    if c.no_match:
        lines.append(
            f"  {c.no_match:>4} no-match (nothing scored above min_confidence)"
        )
    if len(per_source) > 1:
        lines.append("  by source:")
        lines.extend(_format_per_source_lines(per_source))
    return lines


def _format_per_source_lines(per_source: dict[str, _Counts]) -> list[str]:
    """Format the by-source breakdown rows."""
    out: list[str] = []
    for src in sorted(per_source):
        sc = per_source[src]
        parts: list[str] = []
        if sc.auto_write:
            parts.append(f"{sc.auto_write} auto")
        if sc.explicit_id:
            parts.append(f"{sc.explicit_id} id-fetch")
        if sc.prompt_accepted or sc.prompt_declined:
            parts.append(f"{sc.prompt_accepted + sc.prompt_declined} prompted")
        if sc.skip:
            parts.append(f"{sc.skip} skip")
        if sc.no_match:
            parts.append(f"{sc.no_match} no-match")
        out.append(f"    {src}: {', '.join(parts)}")
    return out


# Process-wide singleton.
_STATS = _OutcomeStats()


# Module-level shims so callers don't need to know about the singleton class.
reset = _STATS.reset
record_auto_write = _STATS.record_auto_write
record_prompt_accepted = _STATS.record_prompt_accepted
record_prompt_declined = _STATS.record_prompt_declined
record_skip = _STATS.record_skip
record_no_match = _STATS.record_no_match
record_explicit_id = _STATS.record_explicit_id
has_any_activity = _STATS.has_any_activity
summary_lines = _STATS.summary_lines
