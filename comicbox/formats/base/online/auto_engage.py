"""
Auto-engagement of `api_budget=fast` for large unattended runs.

Comicbox's online lookup is fast enough on small libraries that the
default `balanced` budget is the right pick. At scale — hundreds of
comics on ComicVine, thousands on Metron — `balanced` blows past the
documented rate caps and stretches into multi-hour or multi-day waits.

This module's `resolve_auto_engaged_budget` watches for two signals,
both of which indicate the user is unlikely to want a multi-hour
foreground wait:

- `--unattended` + batch size ≥ per-source `_UNATTENDED_THRESHOLD`
- stdin is not a TTY + batch size ≥ per-source `_NON_TTY_THRESHOLD`
  (4x looser — cron-shaped invocations get the suggestion at a higher
  bar so manual `xargs` pipelines don't surprise the user)

When either fires, the resolved `OnlineSettings` gets a per-source
override pinning `api_budget=fast` for the matching source(s). The user
can suppress with an explicit `--api-budget-per-source <source>:balanced`
or with `--api-budget` set globally to anything non-default.

Thresholds are placeholders from `06-api-budget-spec.md`; Phase B's
calibration data validated the per-source-cap reasoning but didn't pin
the exact curve breakpoints. Revisit when real-world large-library
runs surface call patterns.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from loguru import logger

from comicbox.config.settings import Effort, Prompts

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings


# Batch-size threshold at which to auto-engage `fast` for a source
# under `--unattended`. Per-source because each source's rate cap is
# different (CV: 200/hr; Metron: 1,200/hr + 5,000/day daily cap).
#
# Rationale:
# - ComicVine: at ~10 calls/comic under `balanced` (post-Watchmen fixes),
#   200/hr → ~20 comics/hr. Threshold 50 ≈ 2.5 hours of waiting; a
#   tolerable upper bound on attended use.
# - Metron: at ~6 calls/comic, 1,200/hr → ~200 comics/hr. Threshold
#   500 ≈ 2.5 hours. Day cap (5,000) starts to matter beyond ~800.
_UNATTENDED_THRESHOLDS: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        "comicvine": 50,
        "metron": 500,
    }
)

# 4x the unattended thresholds. The conservative bar for "stdin is not
# a TTY but the user didn't explicitly say unattended" — could be a
# cron job, could be a manual xargs pipeline. Bump the threshold so
# manual invocations don't surprise users; explicit `--unattended` is
# the cleaner signal of intent.
_NON_TTY_THRESHOLDS: Final[MappingProxyType[str, int]] = MappingProxyType(
    {source: count * 4 for source, count in _UNATTENDED_THRESHOLDS.items()}
)


def _stdin_is_tty() -> bool:
    """Return True when stdin is a TTY; wrapper exists for test monkeypatch."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        # Closed stdin / unusual stream — treat as no TTY.
        return False


def _engagement_reason(
    source: str,
    *,
    batch_size: int,
    is_unattended: bool,
    is_tty: bool,
) -> str | None:
    """Return the trigger reason, or None when no trigger fires for `source`."""
    unattended_threshold = _UNATTENDED_THRESHOLDS[source]
    if is_unattended and batch_size >= unattended_threshold:
        return f"batch={batch_size} >= {unattended_threshold}, unattended"
    if not is_tty:
        non_tty_threshold = _NON_TTY_THRESHOLDS[source]
        if batch_size >= non_tty_threshold:
            return f"batch={batch_size} >= {non_tty_threshold}, non-TTY stdin"
    return None


def resolve_auto_engaged_budget(
    online: OnlineSettings, batch_size: int
) -> OnlineSettings:
    """
    Return a possibly-modified `OnlineSettings` with auto-engaged budgets.

    Inputs:
    - `online`: the resolved config (CLI + env + file).
    - `batch_size`: total files to process this run, after `--recurse`
      expansion. Pass 0 or 1 to disable auto-engagement.

    Behavior: walks each known source; for each, if the user did NOT
    set a per-source override AND the global budget is `BALANCED`
    (today's default, also what we want to upgrade FROM), check the
    triggers in order. Per-source override pinned only when at least
    one trigger fires.

    User-set per-source overrides — even to `BALANCED` — block
    auto-engagement for that source. Setting the global `--api-budget`
    to a non-default also blocks auto-engagement (the user has
    spoken).

    Logs an INFO line per source the engagement fires for, so the user
    sees what's happening and knows how to override.
    """
    if batch_size <= 1:
        return online

    # User pinned the global effort to anything non-default → respect it,
    # auto-engagement is for "user didn't choose, we should help" cases.
    if online.tuning.effort is not Effort.BALANCED:
        return online

    from comicbox.config.settings import OnlineSourceTuning

    is_tty = _stdin_is_tty()
    is_unattended = online.lookup.prompts is Prompts.NEVER
    new_per_source = dict(online.tuning.per_source)
    changed = False
    for source in _UNATTENDED_THRESHOLDS:
        existing = new_per_source.get(source)
        if existing is not None and existing.effort is not None:
            # User pinned a per-source override; respect their choice.
            continue
        reason = _engagement_reason(
            source,
            batch_size=batch_size,
            is_unattended=is_unattended,
            is_tty=is_tty,
        )
        if reason is None:
            continue
        base = existing or OnlineSourceTuning()
        new_per_source[source] = replace(base, effort=Effort.MINIMAL)
        changed = True
        logger.info(
            f"online: auto-engaging effort=minimal for {source} "
            f"({reason}). Override under "
            f"online.tuning.per_source.{source}.effort."
        )

    if not changed:
        return online
    new_tuning = replace(online.tuning, per_source=new_per_source)
    return replace(online, tuning=new_tuning)
