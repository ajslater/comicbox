"""
Unit tests for the jobs-accuracy harness's pure functions.

The in-process driver + cache-wipe are exercised by the harness
itself in live runs. These tests cover _diff_outcomes and
build_cli_argv — the bits that don't need a live API.
"""

from __future__ import annotations

from pathlib import Path

from tests.stress.jobs_accuracy import (
    Fixture,
    JobsOutcome,
    _diff_outcomes,
    build_cli_argv,
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
        chosen_by_fixture=chosen,
        decided=decided,
        skipped=len(chosen) - decided,
    )


class TestBuildCliArgv:
    def test_basic_invocation_has_expected_flags(self) -> None:
        argv = build_cli_argv([_fixture("/a.cbz")], jobs=4)
        assert "-n" in argv
        assert "--online" in argv
        assert "--unattended" in argv
        assert "--force-search" in argv
        assert "-j" in argv
        assert "4" in argv
        assert argv[-1] == "/a.cbz"

    def test_threshold_adds_confidence_flag(self) -> None:
        argv = build_cli_argv([_fixture("/a.cbz")], jobs=1, threshold=0.5)
        assert "--confidence-threshold" in argv
        idx = argv.index("--confidence-threshold")
        assert argv[idx + 1] == "metron:0.5"

    def test_no_threshold_omits_confidence_flag(self) -> None:
        argv = build_cli_argv([_fixture("/a.cbz")], jobs=1)
        assert "--confidence-threshold" not in argv

    def test_multiple_fixtures_all_appended(self) -> None:
        argv = build_cli_argv(
            [_fixture("/a.cbz"), _fixture("/b.cbz"), _fixture("/c.cbz")],
            jobs=2,
        )
        assert argv[-3:] == ["/a.cbz", "/b.cbz", "/c.cbz"]


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
