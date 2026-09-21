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


# --------------------------------------- responses that missed the API


def test_summary_buckets_header_less_responses_by_status() -> None:
    """
    The counter Brian can act on: answers that never reached the API.

    Metron's throttles run ahead of all view code and its middleware
    copies `X-RateLimit-*` onto anything they touched, so a response
    without them came from in front of Django. Bucketing by status tells
    a bot-check page (HTTP 200) from a proxy refusal without looking at
    a single body.
    """
    for _ in range(3):
        outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_unthrottled_response("metron", 200)
    outcome_stats.record_unthrottled_response("metron", 200)
    outcome_stats.record_unthrottled_response("metron", 429)

    text = "\n".join(outcome_stats.summary_lines())
    assert "3 responses without rate-limit headers (200: 2, 429: 1)" in text


def test_summary_puts_a_lone_header_less_response_in_the_singular() -> None:
    outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_unthrottled_response("metron", 403)

    text = "\n".join(outcome_stats.summary_lines())
    assert "1 response without rate-limit headers (403: 1)" in text


def test_summary_reports_connection_failures() -> None:
    """Transport failures, which is the shape an IP-level ban takes."""
    outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_connection_failure("metron")
    assert "1 connection failure" in "\n".join(outcome_stats.summary_lines())

    outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_connection_failure("metron")
    assert "2 connection failures" in "\n".join(outcome_stats.summary_lines())


def test_summary_omits_the_new_counters_when_nothing_went_wrong() -> None:
    outcome_stats.record_http_request("metron", "issue_list")

    text = "\n".join(outcome_stats.summary_lines())
    assert "without rate-limit headers" not in text
    assert "connection failure" not in text


def test_api_snapshot_does_not_alias_the_live_counters() -> None:
    """Both mutable members are copied, or a reader could corrupt the run."""
    outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_unthrottled_response("metron", 200)

    snapshot = outcome_stats.api_snapshot()["metron"]
    snapshot.requests["issue_list"] = 99
    snapshot.unthrottled[200] = 99

    live = outcome_stats.api_snapshot()["metron"]
    assert live.requests == {"issue_list": 1}
    assert live.unthrottled == {200: 1}


def test_reset_clears_the_api_counters() -> None:
    outcome_stats.record_http_request("metron", "issue_list")
    outcome_stats.record_unthrottled_response("metron", 200)
    outcome_stats.record_connection_failure("metron")
    assert outcome_stats.has_any_activity() is True

    outcome_stats.reset()

    assert outcome_stats.api_snapshot() == {}
    assert outcome_stats.summary_lines() == []
    assert outcome_stats.has_any_activity() is False


def test_gate_waits_are_recorded_apart_from_the_send() -> None:
    """
    Pacing time comes in on its own hook now.

    mokkari's `rate_limiter` sees the wait; the response hook sees the
    response. Neither knows the other's half, so they report separately
    and the summary adds them up as before.
    """
    outcome_stats.record_gate_wait("metron", 1.5)
    outcome_stats.record_gate_wait("metron", 2.0)
    outcome_stats.record_http_request("metron", "issue_list")

    api = outcome_stats.api_snapshot()["metron"]
    assert api.blocked_seconds == 3.5
    assert api.requests == {"issue_list": 1}
    assert "4s paced" in "\n".join(outcome_stats.summary_lines())


def test_a_send_that_never_answered_is_not_counted_as_a_request() -> None:
    """
    ``requests`` counts responses RECEIVED, which is what the server logs.

    A transport failure produced no response, so it appears only under
    connection failures. It used to be counted under its endpoint too,
    which made comicbox's number disagree with Metron's.
    """
    outcome_stats.record_gate_wait("metron", 0.1)
    outcome_stats.record_connection_failure("metron")

    api = outcome_stats.api_snapshot()["metron"]
    assert api.requests == {}
    assert api.connection_failures == 1
