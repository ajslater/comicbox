"""Tests for `comicbox.formats.base.online.auto_engage.resolve_auto_engaged_budget`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from comicbox.config.settings import (
    Effort,
    OnlineLookupSettings,
    OnlineSettings,
    OnlineSourceTuning,
    OnlineTuningSettings,
    Prompts,
)
from comicbox.formats.base.online.auto_engage import resolve_auto_engaged_budget

if TYPE_CHECKING:
    import pytest


def _settings(
    *,
    effort: Effort = Effort.BALANCED,
    per_source: dict[str, OnlineSourceTuning] | None = None,
    unattended: bool = False,
) -> OnlineSettings:
    lookup = OnlineLookupSettings(
        enabled=True,
        prompts=Prompts.NEVER if unattended else Prompts.ASK,
    )
    tuning = OnlineTuningSettings(
        effort=effort,
        per_source=per_source or {},
    )
    return OnlineSettings(lookup=lookup, tuning=tuning)


def _cv_effort(settings: OnlineSettings) -> Effort | None:
    entry = settings.tuning.per_source.get("comicvine")
    return entry.effort if entry else None


def _metron_effort(settings: OnlineSettings) -> Effort | None:
    entry = settings.tuning.per_source.get("metron")
    return entry.effort if entry else None


def _force_tty(monkeypatch: pytest.MonkeyPatch, *, is_tty: bool) -> None:
    """Pin `_stdin_is_tty()` for test determinism."""
    monkeypatch.setattr(
        "comicbox.formats.base.online.auto_engage._stdin_is_tty", lambda: is_tty
    )


# --------------------------------------------------------- no-op branches


def test_no_op_when_batch_size_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single-file invocations never auto-engage — interactive use."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=1)
    assert result is settings


def test_no_op_when_batch_size_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty path list → no engagement (nothing to engage for)."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=0)
    assert result is settings


def test_no_op_when_global_effort_not_balanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User pinned --effort thorough → respect, never auto-engage."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(effort=Effort.THOROUGH, unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


def test_no_op_when_global_effort_already_minimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User pinned --effort minimal → already minimal, no engagement needed."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(effort=Effort.MINIMAL, unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


def test_no_op_when_attended_and_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """No --prompts never, TTY present → user is at keyboard, no engagement."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=False)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


# --------------------------------------------------------- unattended trigger


def test_unattended_engages_comicvine_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--prompts never` + batch ≥ 50 → engage minimal for ComicVine."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert _cv_effort(result) == Effort.MINIMAL


def test_unattended_below_cv_threshold_does_not_engage_cv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--prompts never` + batch < 50 → no CV engagement."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=49)
    assert "comicvine" not in result.tuning.per_source


def test_metron_never_auto_engages_unattended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Metron never auto-engages, at any batch size.

    Its single-call search costs the same at every effort (PR #143), so
    `fast` can't reduce it — auto-engaging would be a misleading no-op.
    Only fan-out sources (ComicVine) are eligible.
    """
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    # A batch far past any historical Metron threshold.
    result = resolve_auto_engaged_budget(settings, batch_size=100_000)
    assert _cv_effort(result) == Effort.MINIMAL
    assert _metron_effort(result) is None
    assert "metron" not in result.tuning.per_source


# --------------------------------------------------------- non-TTY trigger


def test_non_tty_uses_stricter_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-TTY without --prompts never → 4x the threshold (200 for CV)."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=False)
    # Batch 50 — would engage under --prompts never, doesn't under non-TTY.
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert "comicvine" not in result.tuning.per_source

    # Batch 200 — over the 4x non-TTY threshold.
    result = resolve_auto_engaged_budget(settings, batch_size=200)
    assert _cv_effort(result) == Effort.MINIMAL


def test_metron_never_auto_engages_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metron stays out of auto-engagement on the non-TTY path too."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=False)
    result = resolve_auto_engaged_budget(settings, batch_size=100_000)
    assert _cv_effort(result) == Effort.MINIMAL
    assert _metron_effort(result) is None


# --------------------------------------------------------- user overrides


def test_per_source_override_blocks_engagement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Explicit per-source override blocks engagement.

    User has spoken — auto-engagement is for "user didn't choose, we
    should help" cases, not "we know better than the user."
    """
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(
        unattended=True,
        per_source={"comicvine": OnlineSourceTuning(effort=Effort.BALANCED)},
    )
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    # CV override is preserved (not bumped to minimal).
    assert _cv_effort(result) == Effort.BALANCED
    # Metron is never a candidate for auto-engagement.
    assert _metron_effort(result) is None


def test_logs_engagement_decision(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auto-engagement logs an INFO line per source it fires for."""
    import logging

    from loguru import logger as loguru_logger

    _force_tty(monkeypatch, is_tty=True)
    # Bridge loguru → caplog. Standard pattern.
    handler_id = loguru_logger.add(caplog.handler, level=0)
    try:
        caplog.set_level(logging.INFO)
        settings = _settings(unattended=True)
        resolve_auto_engaged_budget(settings, batch_size=500)
    finally:
        loguru_logger.remove(handler_id)
    messages = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "auto-engaging effort=minimal for comicvine" in messages
    # Metron never auto-engages, so it's never logged.
    assert "for metron" not in messages
    # Override hint is present.
    assert "online.tuning.per_source.comicvine.effort" in messages


def test_returns_new_settings_object_when_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A change produces a new OnlineSettings; original is untouched."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert result is not settings  # new object
    # Original untouched (frozen dataclass — defensive double-check).
    assert settings.tuning.per_source == {}
    assert _cv_effort(result) == Effort.MINIMAL
