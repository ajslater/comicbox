"""
Unit tests for the jobs-accuracy harness's pure functions.

Subprocess + cache-wipe are exercised by the harness itself in live
runs. These tests cover parse_chosen_ids and _diff_outcomes — the
bits that determine which fixture got which decision and how that
compares across jobs values.
"""

from __future__ import annotations

from pathlib import Path

from tests.stress.jobs_accuracy import (
    Fixture,
    JobsOutcome,
    _diff_outcomes,
    parse_chosen_ids,
)


def _fixture(path: str, metron: int | None = None) -> Fixture:
    return Fixture(path=Path(path), metron=metron, comicvine=None)


def _outcome(
    jobs: int,
    chosen: dict[str, int | None],
    wall: float = 60.0,
) -> JobsOutcome:
    decided = sum(1 for v in chosen.values() if v is not None)
    return JobsOutcome(
        jobs=jobs,
        wall_seconds=wall,
        log_path=Path("/tmp/x.log"),
        chosen_by_fixture=chosen,
        decided=decided,
        skipped=len(chosen) - decided,
    )


def _write_log(tmp_path: Path, content: str) -> Path:
    log = tmp_path / "run.log"
    log.write_text(content)
    return log


class TestParseChosenIds:
    def test_no_auto_writes_returns_all_none(self, tmp_path: Path) -> None:
        fixtures = [_fixture("/lib/a.cbz"), _fixture("/lib/b.cbz")]
        log = _write_log(tmp_path, "nothing relevant here\n")
        result = parse_chosen_ids(log, fixtures)
        assert result == {"/lib/a.cbz": None, "/lib/b.cbz": None}

    def test_path_then_auto_write_assigns_correctly(self, tmp_path: Path) -> None:
        fixtures = [_fixture("/lib/a.cbz"), _fixture("/lib/b.cbz")]
        log = _write_log(
            tmp_path,
            "processing /lib/a.cbz\n"
            "INFO     | online metron: auto-writing id=42 (score=0.99)\n"
            "processing /lib/b.cbz\n"
            "INFO     | online metron: auto-writing id=99 (score=0.97)\n",
        )
        result = parse_chosen_ids(log, fixtures)
        assert result == {"/lib/a.cbz": 42, "/lib/b.cbz": 99}

    def test_skipped_fixture_keeps_none(self, tmp_path: Path) -> None:
        fixtures = [_fixture("/lib/a.cbz"), _fixture("/lib/b.cbz")]
        log = _write_log(
            tmp_path,
            "processing /lib/a.cbz\n"
            "INFO     | online metron: skipped (matcher declined)\n"
            "processing /lib/b.cbz\n"
            "INFO     | online metron: auto-writing id=99 (score=0.97)\n",
        )
        result = parse_chosen_ids(log, fixtures)
        assert result == {"/lib/a.cbz": None, "/lib/b.cbz": 99}

    def test_ignores_other_sources(self, tmp_path: Path) -> None:
        fixtures = [_fixture("/lib/a.cbz")]
        log = _write_log(
            tmp_path,
            "processing /lib/a.cbz\n"
            "INFO     | online comicvine: auto-writing id=12345 (score=0.99)\n",
        )
        # CV auto-write should NOT be recorded — harness is Metron-only.
        result = parse_chosen_ids(log, fixtures)
        assert result == {"/lib/a.cbz": None}


class TestDiffOutcomes:
    def test_identical_outcomes_all_same(self) -> None:
        base = _outcome(1, {"/a": 1, "/b": 2, "/c": None})
        other = _outcome(8, {"/a": 1, "/b": 2, "/c": None})
        diff = _diff_outcomes(base, other)
        assert diff.same == 3
        assert diff.changed == []
        assert diff.lost == []
        assert diff.gained == []
        assert diff.total == 3

    def test_changed_id_categorised(self) -> None:
        base = _outcome(1, {"/a": 1})
        other = _outcome(8, {"/a": 99})
        diff = _diff_outcomes(base, other)
        assert diff.same == 0
        assert diff.changed == [("/a", 1, 99)]
        assert diff.lost == []
        assert diff.gained == []

    def test_lost_when_parallel_skips_what_serial_decided(self) -> None:
        base = _outcome(1, {"/a": 42})
        other = _outcome(8, {"/a": None})
        diff = _diff_outcomes(base, other)
        assert diff.lost == [("/a", 42)]
        assert diff.changed == []
        assert diff.gained == []

    def test_gained_when_parallel_decides_what_serial_skipped(self) -> None:
        base = _outcome(1, {"/a": None})
        other = _outcome(8, {"/a": 7})
        diff = _diff_outcomes(base, other)
        assert diff.gained == [("/a", 7)]
        assert diff.changed == []
        assert diff.lost == []

    def test_mixed_categories(self) -> None:
        base = _outcome(1, {"/a": 1, "/b": 2, "/c": None, "/d": 4})
        other = _outcome(8, {"/a": 1, "/b": None, "/c": 3, "/d": 99})
        diff = _diff_outcomes(base, other)
        assert diff.same == 1  # /a
        assert diff.lost == [("/b", 2)]
        assert diff.gained == [("/c", 3)]
        assert diff.changed == [("/d", 4, 99)]
        assert diff.total == 4
