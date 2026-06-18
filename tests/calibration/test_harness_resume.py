"""
Calibration-harness tests: --resume chunked-run support + end-of-run _save_outcomes.

Split from test_harness.py to keep per-file maintainability index healthy.
The shared `_outcome` / `_make_fixture` / `_write_outcomes` factories live
in ``tests.calibration._harness_helpers``.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.calibration._harness_helpers import (
    make_fixture,
    make_outcome,
    write_outcomes,
)
from tests.calibration.run import _Fixture, _Outcome

_outcome = make_outcome
_make_fixture = make_fixture
_write_outcomes = write_outcomes


# ---------------------------------------------- --resume (chunked-run support)


def test_load_done_files_returns_all_paths_regardless_of_outcome(
    tmp_path: Path,
) -> None:
    """`--resume` skips ANY fixture present — correct, wrong, even errored."""
    from tests.calibration.run import _load_done_files

    out = tmp_path / "fixtures.outcomes.json"
    out.write_text(
        json.dumps(
            [
                {"file": "/a.cbz", "outcome": "correct"},
                {"file": "/b.cbz", "outcome": "wrong"},
                {"file": "/c.cbz", "outcome": "error"},
                {"file": "/d.cbz", "outcome": "no_candidates"},
            ]
        )
    )
    assert _load_done_files(out) == {"/a.cbz", "/b.cbz", "/c.cbz", "/d.cbz"}


def test_load_done_files_empty_for_missing_file(tmp_path: Path) -> None:
    """No outcomes file → empty set (resume is a no-op)."""
    from tests.calibration.run import _load_done_files

    assert _load_done_files(tmp_path / "nothing.json") == set()


def test_filter_skip_done_drops_listed_paths(tmp_path: Path) -> None:
    from tests.calibration.run import _filter_skip_done

    f_a = _make_fixture(tmp_path / "a.cbz")
    f_b = _make_fixture(tmp_path / "b.cbz")
    f_c = _make_fixture(tmp_path / "c.cbz")
    done = {str(tmp_path / "a.cbz"), str(tmp_path / "c.cbz")}
    assert _filter_skip_done([f_a, f_b, f_c], done) == [f_b]


def test_resolve_resume_source_path_prefers_labeled(tmp_path: Path) -> None:
    """When --label is set, resume reads from the labeled file."""
    from tests.calibration.run import _resolve_resume_source_path

    fp = tmp_path / "fixtures.json"
    full = tmp_path / "fixtures.outcomes.json"
    labeled = tmp_path / "fixtures.outcomes.chunk1.json"
    full.write_text("[]")
    labeled.write_text("[]")
    assert _resolve_resume_source_path(fp, label="chunk1") == labeled


def test_resolve_resume_source_path_labeled_missing_returns_none(
    tmp_path: Path,
) -> None:
    """Label set but labeled file doesn't exist → None (start fresh)."""
    from tests.calibration.run import _resolve_resume_source_path

    fp = tmp_path / "fixtures.json"
    # Canonical exists, but we asked for a label that doesn't.
    (tmp_path / "fixtures.outcomes.json").write_text("[]")
    assert _resolve_resume_source_path(fp, label="missing") is None


def test_resolve_resume_source_path_no_label_uses_retry_resolution(
    tmp_path: Path,
) -> None:
    """No label → falls back to full-then-partial resolution."""
    from tests.calibration.run import _resolve_resume_source_path

    fp = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    partial.write_text("[]")
    assert _resolve_resume_source_path(fp, label=None) == partial


def test_resolve_resume_source_path_nothing_exists_returns_none(
    tmp_path: Path,
) -> None:
    """No files anywhere → None (resume is a no-op, not an error)."""
    from tests.calibration.run import _resolve_resume_source_path

    assert _resolve_resume_source_path(tmp_path / "fixtures.json", label=None) is None


def test_apply_filters_resume_skips_done_fixtures(tmp_path: Path) -> None:
    """End-to-end: --resume drops fixtures already in canonical outcomes file."""
    from tests.calibration.run import _apply_filters

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    _write_outcomes(canonical, str(tmp_path / "done.cbz"), "correct")

    fixtures = [
        _Fixture(tmp_path / "done.cbz", {"metron": 1}, "full"),
        _Fixture(tmp_path / "todo.cbz", {"metron": 2}, "full"),
    ]
    out = _apply_filters(
        fixtures,
        fixtures_path=fp,
        retry_misses=False,
        resume=True,
        label=None,
        name_filter=None,
        one_per_series=False,
        limit=None,
    )
    assert [f.file_path.name for f in out] == ["todo.cbz"]


def test_apply_filters_resume_reads_labeled_file(tmp_path: Path) -> None:
    """--resume with --label reads from the labeled outcomes, not the canonical."""
    from tests.calibration.run import _apply_filters

    fp = tmp_path / "fixtures.json"
    # Canonical says A is done — but we're labeling, so canonical is irrelevant.
    _write_outcomes(
        tmp_path / "fixtures.outcomes.json", str(tmp_path / "a.cbz"), "correct"
    )
    # Labeled says B is done — that's what should drive the skip.
    _write_outcomes(
        tmp_path / "fixtures.outcomes.chunk1.json",
        str(tmp_path / "b.cbz"),
        "correct",
    )

    fixtures = [
        _Fixture(tmp_path / "a.cbz", {"metron": 1}, "full"),
        _Fixture(tmp_path / "b.cbz", {"metron": 2}, "full"),
    ]
    out = _apply_filters(
        fixtures,
        fixtures_path=fp,
        retry_misses=False,
        resume=True,
        label="chunk1",
        name_filter=None,
        one_per_series=False,
        limit=None,
    )
    # Only 'b' was in the labeled file → 'a' survives.
    assert [f.file_path.name for f in out] == ["a.cbz"]


def test_apply_filters_resume_no_outcomes_file_is_noop(tmp_path: Path) -> None:
    """--resume with no prior outcomes file behaves like an unfiltered run."""
    from tests.calibration.run import _apply_filters

    fp = tmp_path / "fixtures.json"
    fixtures = [
        _Fixture(tmp_path / "a.cbz", {"metron": 1}, "full"),
        _Fixture(tmp_path / "b.cbz", {"metron": 2}, "full"),
    ]
    out = _apply_filters(
        fixtures,
        fixtures_path=fp,
        retry_misses=False,
        resume=True,
        label=None,
        name_filter=None,
        one_per_series=False,
        limit=None,
    )
    assert len(out) == 2


def test_build_checkpoint_resume_merges_into_canonical(tmp_path: Path) -> None:
    """--resume without --label → MERGE into canonical so chunks accumulate."""
    from tests.calibration.run import _build_checkpoint, _serialize_outcomes

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    # Chunk-1: pretend a previous run wrote one outcome.
    _serialize_outcomes(
        [
            _Outcome(
                fixture=_Fixture(Path("/chunk1.cbz"), {"metron": 1}, "full"),
                source_name="metron",
                top_score=0.99,
                top_issue_id=1,
                top_correct=True,
                n_candidates=3,
            )
        ],
        canonical,
    )

    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=canonical,
        label=None,
        was_filtered=True,  # --limit makes this True; resume should override
        resume=True,
    )
    cp([_outcome(source="comicvine", score=0.88)])

    payload = json.loads(canonical.read_text())
    files = {e["file"] for e in payload}
    # Both the chunk-1 entry AND the new chunk-2 entry survive.
    assert "/chunk1.cbz" in files
    assert "/x.cbz" in files


def test_build_checkpoint_resume_with_label_merges_into_labeled(tmp_path: Path) -> None:
    """--resume + --label → merge into the labeled file."""
    from tests.calibration.run import _build_checkpoint

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    labeled = tmp_path / "fixtures.outcomes.exp1.json"

    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=canonical,
        label="exp1",
        was_filtered=False,
        resume=True,
    )
    cp([_outcome(score=0.9)])
    # Labeled file gets the data; canonical stays untouched.
    assert labeled.exists()
    assert not canonical.exists()


# --- _save_outcomes (end-of-run) ---


def test_save_outcomes_resume_merges_into_canonical(tmp_path: Path) -> None:
    """End-of-run save with --resume merges (chunks accumulate)."""
    from tests.calibration.run import _save_outcomes, _serialize_outcomes

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    _serialize_outcomes(
        [
            _Outcome(
                fixture=_Fixture(Path("/old.cbz"), {"metron": 1}, "full"),
                source_name="metron",
                top_score=0.99,
                top_issue_id=1,
                top_correct=True,
                n_candidates=3,
            )
        ],
        canonical,
    )
    _save_outcomes(
        [_outcome(source="comicvine", score=0.88)],
        fixtures_path=fp,
        outcomes_path=canonical,
        label=None,
        was_filtered=True,
        resume=True,
    )
    files = {e["file"] for e in json.loads(canonical.read_text())}
    assert files == {"/old.cbz", "/x.cbz"}


def test_save_outcomes_label_only_overwrites_labeled(tmp_path: Path) -> None:
    """--label without --resume overwrites the labeled file (Phase B behavior)."""
    from tests.calibration.run import _save_outcomes

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    labeled = tmp_path / "fixtures.outcomes.exp1.json"
    labeled.write_text(json.dumps([{"file": "/stale.cbz", "outcome": "correct"}]))

    _save_outcomes(
        [_outcome(score=0.9)],
        fixtures_path=fp,
        outcomes_path=canonical,
        label="exp1",
        was_filtered=False,
        resume=False,
    )
    files = {e["file"] for e in json.loads(labeled.read_text())}
    # The stale entry got overwritten — labeled runs are non-merging.
    assert files == {"/x.cbz"}


def test_save_outcomes_full_run_overwrites_canonical(tmp_path: Path) -> None:
    from tests.calibration.run import _save_outcomes

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    _save_outcomes(
        [_outcome(score=0.9)],
        fixtures_path=fp,
        outcomes_path=canonical,
        label=None,
        was_filtered=False,
        resume=False,
    )
    assert canonical.exists()
    files = {e["file"] for e in json.loads(canonical.read_text())}
    assert files == {"/x.cbz"}


def test_save_outcomes_filtered_merges_into_partial(tmp_path: Path) -> None:
    from tests.calibration.run import _save_outcomes, _serialize_outcomes

    fp = tmp_path / "fixtures.json"
    canonical = tmp_path / "fixtures.outcomes.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _serialize_outcomes(
        [
            _Outcome(
                fixture=_Fixture(Path("/old.cbz"), {"metron": 1}, "full"),
                source_name="metron",
                top_score=0.99,
                top_issue_id=1,
                top_correct=True,
                n_candidates=3,
            )
        ],
        partial,
    )
    _save_outcomes(
        [_outcome(source="metron", score=0.88, correct=False)],
        fixtures_path=fp,
        outcomes_path=canonical,
        label=None,
        was_filtered=True,
        resume=False,
    )
    files = {e["file"] for e in json.loads(partial.read_text())}
    assert files == {"/old.cbz", "/x.cbz"}
