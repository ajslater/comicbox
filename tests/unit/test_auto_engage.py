"""Tests for `comicbox.formats.base.online.auto_engage.resolve_auto_engaged_budget`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from comicbox.config.settings import APIBudget, OnlineSettings
from comicbox.formats.base.online.auto_engage import resolve_auto_engaged_budget

if TYPE_CHECKING:
    import pytest


def _settings(
    *,
    api_budget: APIBudget = APIBudget.BALANCED,
    api_budget_per_source: dict[str, APIBudget] | None = None,
    unattended: bool = False,
) -> OnlineSettings:
    return OnlineSettings(
        enabled=True,
        api_budget=api_budget,
        api_budget_per_source=api_budget_per_source or {},
        unattended=unattended,
    )


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


def test_no_op_when_global_budget_not_balanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User pinned --api-budget exhaustive → respect, never auto-engage."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(api_budget=APIBudget.EXHAUSTIVE, unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


def test_no_op_when_global_budget_already_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User pinned --api-budget fast → already fast, no engagement needed."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(api_budget=APIBudget.FAST, unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


def test_no_op_when_attended_and_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """No --unattended, TTY present → user is at keyboard, no engagement."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=False)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result is settings


# --------------------------------------------------------- unattended trigger


def test_unattended_engages_comicvine_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--unattended` + batch ≥ 50 → engage fast for ComicVine."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert result.api_budget_per_source["comicvine"] == APIBudget.FAST


def test_unattended_below_cv_threshold_does_not_engage_cv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--unattended` + batch < 50 → no CV engagement."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=49)
    assert "comicvine" not in result.api_budget_per_source


def test_unattended_metron_threshold_higher_than_cv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CV engages at 50; Metron only at 500 (more forgiving rate cap)."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    # Batch 100 — over CV's 50, under Metron's 500.
    result = resolve_auto_engaged_budget(settings, batch_size=100)
    assert result.api_budget_per_source["comicvine"] == APIBudget.FAST
    assert "metron" not in result.api_budget_per_source


def test_unattended_engages_metron_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--unattended` + batch ≥ 500 → engage fast for Metron too."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    assert result.api_budget_per_source["comicvine"] == APIBudget.FAST
    assert result.api_budget_per_source["metron"] == APIBudget.FAST


# --------------------------------------------------------- non-TTY trigger


def test_non_tty_uses_stricter_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-TTY without --unattended → 4x the threshold (200 for CV)."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=False)
    # Batch 50 — would engage under --unattended, doesn't under non-TTY.
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert "comicvine" not in result.api_budget_per_source

    # Batch 200 — over the 4x non-TTY threshold.
    result = resolve_auto_engaged_budget(settings, batch_size=200)
    assert result.api_budget_per_source["comicvine"] == APIBudget.FAST


def test_non_tty_engages_metron_at_2000(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metron's non-TTY threshold is 500*4 = 2000."""
    _force_tty(monkeypatch, is_tty=False)
    settings = _settings(unattended=False)
    result = resolve_auto_engaged_budget(settings, batch_size=2000)
    assert result.api_budget_per_source["metron"] == APIBudget.FAST


# --------------------------------------------------------- user overrides


def test_per_source_override_blocks_engagement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Explicit `--api-budget-per-source comicvine:balanced` blocks engagement.

    User has spoken — auto-engagement is for "user didn't choose, we
    should help" cases, not "we know better than the user."
    """
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(
        unattended=True,
        api_budget_per_source={"comicvine": APIBudget.BALANCED},
    )
    result = resolve_auto_engaged_budget(settings, batch_size=500)
    # CV override is preserved (not bumped to fast).
    assert result.api_budget_per_source["comicvine"] == APIBudget.BALANCED
    # Metron still engages (no per-source override blocks it).
    assert result.api_budget_per_source["metron"] == APIBudget.FAST


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
    assert "auto-engaging api_budget=fast for comicvine" in messages
    assert "auto-engaging api_budget=fast for metron" in messages
    # Override hint is present.
    assert "--api-budget-per-source comicvine:balanced" in messages


def test_returns_new_settings_object_when_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A change produces a new OnlineSettings; original is untouched."""
    _force_tty(monkeypatch, is_tty=True)
    settings = _settings(unattended=True)
    result = resolve_auto_engaged_budget(settings, batch_size=50)
    assert result is not settings  # new object
    # Original untouched (frozen dataclass — defensive double-check).
    assert settings.api_budget_per_source == {}
    assert result.api_budget_per_source == {"comicvine": APIBudget.FAST}
