"""Outcome-stats tracking + summary tests."""

from __future__ import annotations

from comicbox.formats.base.online import outcome_stats


def setup_function() -> None:
    outcome_stats.reset()


def test_summary_empty_when_no_activity() -> None:
    assert outcome_stats.summary_lines() == []
    assert outcome_stats.has_any_activity() is False


def test_summary_counts_outcomes() -> None:
    outcome_stats.record_auto_write("metron")
    outcome_stats.record_auto_write("metron")
    outcome_stats.record_skip("metron")
    outcome_stats.record_no_match("comicvine")
    outcome_stats.record_prompt_accepted("comicvine")
    outcome_stats.record_prompt_declined("comicvine")
    outcome_stats.record_explicit_id("metron")

    lines = outcome_stats.summary_lines()
    text = "\n".join(lines)
    assert "Online tagging summary" in text
    assert "2 auto-written" in text
    assert "1 fetched by --id" in text
    assert "2 prompted (chose 1, declined 1)" in text
    assert "1 skipped" in text
    assert "1 no-match" in text
    # Per-source breakdown shows up when >1 source recorded.
    assert "by source:" in text
    assert "metron:" in text
    assert "comicvine:" in text


def test_summary_omits_zero_buckets() -> None:
    outcome_stats.record_auto_write("metron")
    text = "\n".join(outcome_stats.summary_lines())
    assert "auto-written" in text
    assert "no-match" not in text
    assert "skipped" not in text
    # With only one source recorded, the per-source breakdown is omitted.
    assert "by source:" not in text


def test_reset_clears_state() -> None:
    outcome_stats.record_auto_write("metron")
    assert outcome_stats.has_any_activity() is True
    outcome_stats.reset()
    assert outcome_stats.has_any_activity() is False
    assert outcome_stats.summary_lines() == []
