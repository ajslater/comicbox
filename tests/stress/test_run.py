"""
Unit tests for the stress-test harness's pure functions.

The subprocess and cache-wipe paths need real comicbox + live APIs, so
those are exercised by the harness itself in live runs (see README.md).
These tests cover the log-parsing, rate-check formatting, and summary
formatting — the bits that determine pass/fail decisions.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from tests.stress.run import (
    CacheSnapshot,
    RunResult,
    build_summary,
    format_rate_check,
    parse_log,
)


def _write_log(tmp_path: Path, content: str) -> Path:
    log = tmp_path / "run.log"
    log.write_text(content)
    return log


class TestParseLog:
    def test_empty_log(self, tmp_path: Path) -> None:
        log = _write_log(tmp_path, "")
        m = parse_log(log)
        assert m == {
            "rate_limit_retries": 0,
            "warnings": 0,
            "errors": 0,
            "exceptions": 0,
        }

    def test_counts_rate_limit_retries(self, tmp_path: Path) -> None:
        log = _write_log(
            tmp_path,
            "issue: rate-limit, retrying in 30.0s (rate-limit attempt 1/5)\n"
            "issue: rate-limit, retrying in 60.0s (rate-limit attempt 2/5)\n"
            "issue: HTTPError, retrying in 1.0s\n",
        )
        m = parse_log(log)
        assert m["rate_limit_retries"] == 2

    def test_filters_dry_run_no_action_from_warnings(self, tmp_path: Path) -> None:
        log = _write_log(
            tmp_path,
            "WARNING  | No action performed\n"
            "WARNING  | No action performed\n"
            "WARNING  | online: cover download failed\n",
        )
        m = parse_log(log)
        assert m["warnings"] == 1

    def test_counts_tracebacks(self, tmp_path: Path) -> None:
        log = _write_log(
            tmp_path,
            "some line\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1, in <module>\n'
            "Exception: boom\n"
            "Traceback (most recent call last):\n"
            "Exception: boom2\n",
        )
        m = parse_log(log)
        assert m["exceptions"] == 2

    def test_missing_log_is_safe(self, tmp_path: Path) -> None:
        m = parse_log(tmp_path / "does-not-exist.log")
        assert m["exceptions"] == 0


class TestFormatRateCheck:
    def test_metron_within_cap_is_ok(self) -> None:
        # 10 req in 60s = 10/min, under Metron's 20/min cap.
        row = format_rate_check("metron", requests=10, wall_seconds=60.0)
        assert "| metron | 10 |" in row
        assert "OK" in row

    def test_metron_over_per_minute_cap_flags_over(self) -> None:
        # 30 req in 60s = 30/min, over Metron's 20/min cap by 50%.
        row = format_rate_check("metron", requests=30, wall_seconds=60.0)
        assert "OVER (30.0/min vs 20)" in row

    def test_short_burst_does_not_flag_hourly_cap(self) -> None:
        # 30 CV req in 36s projects to 3001/hr but wall < 3600s, so the
        # hourly cap is unevaluable. Per-minute (50/min) is under the
        # 60/min cap, so this is OK.
        row = format_rate_check("comicvine", requests=30, wall_seconds=36.0)
        assert "OK" in row
        assert "hourly" not in row.lower()

    def test_long_run_does_flag_hourly_cap_violation(self) -> None:
        # 250 CV req in 1 hour exceeds 200/hr cap.
        row = format_rate_check("comicvine", requests=250, wall_seconds=3600.0)
        assert "OVER hourly (250/hr vs 200)" in row

    def test_unknown_source_no_caps(self) -> None:
        row = format_rate_check("madeup", requests=999, wall_seconds=60.0)
        assert "| madeup |" in row
        assert "OK" in row


class TestBuildSummary:
    def _make_result(
        self,
        *,
        wall_seconds: float = 60.0,
        cv_delta: int = 0,
        metron_delta: int = 0,
        exceptions: int = 0,
        exit_code: int = 0,
    ) -> RunResult:
        args = Namespace(
            jobs=8,
            sources="metron,comicvine",
            no_wipe_cache=False,
        )
        before = CacheSnapshot(
            rows={"metron": 0, "comicvine": 0},
            bytes={"metron": 0, "comicvine": 0},
        )
        after = CacheSnapshot(
            rows={"metron": metron_delta, "comicvine": cv_delta},
            bytes={"metron": 0, "comicvine": 0},
        )
        return RunResult(
            args=args,
            fixture_count=20,
            fixtures_root=Path("/fixtures"),
            wall_seconds=wall_seconds,
            before=before,
            after=after,
            metrics={
                "rate_limit_retries": 0,
                "warnings": 0,
                "errors": 0,
                "exceptions": exceptions,
            },
            exit_code=exit_code,
            log_path=Path("/tmp/run.log"),
        )

    def test_clean_run_is_pass(self) -> None:
        summary = build_summary(self._make_result())
        assert "**PASS**" in summary

    def test_nonzero_exit_is_fail(self) -> None:
        summary = build_summary(self._make_result(exit_code=2))
        assert "**FAIL**" in summary
        assert "non-zero status (2)" in summary

    def test_traceback_is_fail(self) -> None:
        summary = build_summary(self._make_result(exceptions=1))
        assert "**FAIL**" in summary
        assert "traceback" in summary.lower()

    def test_per_minute_cap_violation_is_fail(self) -> None:
        # 30/min Metron over 20/min cap.
        summary = build_summary(self._make_result(metron_delta=30, wall_seconds=60.0))
        assert "**FAIL**" in summary
        assert "metron exceeded documented cap" in summary
