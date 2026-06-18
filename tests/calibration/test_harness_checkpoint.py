"""
Calibration-harness tests: partial-outcomes merge, api-call diff, atomic write + checkpointing.

Split from test_harness.py to keep per-file maintainability index healthy.
The shared `_outcome` / `_make_fixture` factories live in
``tests.calibration._harness_helpers``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from tests.calibration._harness_helpers import make_fixture, make_outcome
from tests.calibration.run import _Fixture, _Outcome

if TYPE_CHECKING:
    import pytest

_outcome = make_outcome
_make_fixture = make_fixture


# --------------------------------------- partial-outcomes merge semantics


def test_merge_writes_fresh_when_file_missing(tmp_path: Path) -> None:
    """First filtered run writes; subsequent ones merge."""
    from tests.calibration.run import _merge_outcomes_to_partial

    path = tmp_path / "fixtures.outcomes.partial.json"
    new_outcomes = [_outcome(source="metron", score=0.99, correct=True)]
    _merge_outcomes_to_partial(path, new_outcomes)
    assert path.exists()
    [entry] = json.loads(path.read_text())
    assert entry["outcome"] == "correct"


def test_merge_preserves_other_fixtures_when_retrying_subset(
    tmp_path: Path,
) -> None:
    """
    The smoking gun: retrying just Watchmen shouldn't wipe Conan's miss.

    This is the bug we shipped: each --retry-misses overwrote the partial
    with just its subset, so successful retries silently destroyed the
    record of which other fixtures were still broken.
    """
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "fixtures.outcomes.partial.json"
    # Existing partial: three misses across three different families.
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/Watchmen.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.89,
            top_issue_id=2,
            top_correct=False,
            n_candidates=3,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/Conan.cbz"), comicvine=10),
            source_name="comicvine",
            top_score=0.0,
            top_issue_id=None,
            top_correct=None,
            n_candidates=0,
        ),
        _Outcome(
            fixture=_make_fixture(Path("/LoisLane.cbz"), comicvine=20),
            source_name="comicvine",
            top_score=0.78,
            top_issue_id=21,
            top_correct=False,
            n_candidates=2,
        ),
    ]
    _serialize_outcomes(existing, path)

    # Retry just Watchmen — it now passes.
    new = [
        _Outcome(
            fixture=_make_fixture(Path("/Watchmen.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.95,
            top_issue_id=1,
            top_correct=True,
            n_candidates=3,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    by_file = {entry["file"]: entry for entry in merged}
    # All three fixtures are still present.
    assert set(by_file) == {"/Watchmen.cbz", "/Conan.cbz", "/LoisLane.cbz"}
    # Watchmen got updated to correct.
    assert by_file["/Watchmen.cbz"]["outcome"] == "correct"
    # The other two are preserved with their original miss outcomes.
    assert by_file["/Conan.cbz"]["outcome"] == "no_candidates"
    assert by_file["/LoisLane.cbz"]["outcome"] == "wrong"


def test_merge_keys_by_file_and_source(tmp_path: Path) -> None:
    """Same file with two sources gets two independent entries."""
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "outcomes.partial.json"
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="metron",
            top_score=0.0,
            top_issue_id=None,
            top_correct=False,
            n_candidates=0,
            error="boom",
        ),
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="comicvine",
            top_score=0.99,
            top_issue_id=2,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _serialize_outcomes(existing, path)

    # Retry just the metron side; it now passes.
    new = [
        _Outcome(
            fixture=_make_fixture(Path("/x.cbz"), metron=1, comicvine=2),
            source_name="metron",
            top_score=0.97,
            top_issue_id=1,
            top_correct=True,
            n_candidates=3,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    by_key = {(e["file"], e["source"]): e for e in merged}
    # Metron side updated; CV side preserved.
    assert by_key[("/x.cbz", "metron")]["outcome"] == "correct"
    assert by_key[("/x.cbz", "comicvine")]["outcome"] == "correct"
    # No duplicates created.
    assert len(merged) == 2


def test_merge_appends_new_entries(tmp_path: Path) -> None:
    """A fixture not in the existing partial gets appended."""
    from tests.calibration.run import _merge_outcomes_to_partial, _serialize_outcomes

    path = tmp_path / "outcomes.partial.json"
    existing = [
        _Outcome(
            fixture=_make_fixture(Path("/old.cbz"), comicvine=1),
            source_name="comicvine",
            top_score=0.0,
            top_issue_id=None,
            top_correct=False,
            n_candidates=0,
        ),
    ]
    _serialize_outcomes(existing, path)

    new = [
        _Outcome(
            fixture=_make_fixture(Path("/new.cbz"), comicvine=2),
            source_name="comicvine",
            top_score=0.95,
            top_issue_id=2,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    files = [e["file"] for e in merged]
    assert files == ["/old.cbz", "/new.cbz"]  # existing first, new appended


def test_merge_preserves_existing_extra_keys(tmp_path: Path) -> None:
    """
    Entries in the existing file that have keys we don't recognize survive.

    Future-proofs the merge against schema additions: if a previous
    `comicbox` version wrote outcome fields we no longer emit, those
    fields stay on un-retried entries. New writes use the current
    schema; existing un-touched entries keep theirs.
    """
    from tests.calibration.run import _merge_outcomes_to_partial

    path = tmp_path / "outcomes.partial.json"
    # Hand-crafted entry with a future-only field.
    path.write_text(
        json.dumps(
            [
                {
                    "file": "/preserved.cbz",
                    "source": "metron",
                    "outcome": "wrong",
                    "top_score": 0.5,
                    "future_field": "kept",
                }
            ]
        )
    )

    new = [
        _Outcome(
            fixture=_make_fixture(Path("/new.cbz"), metron=1),
            source_name="metron",
            top_score=0.99,
            top_issue_id=1,
            top_correct=True,
            n_candidates=1,
        ),
    ]
    _merge_outcomes_to_partial(path, new)

    merged = json.loads(path.read_text())
    preserved = next(e for e in merged if e["file"] == "/preserved.cbz")
    assert preserved["future_field"] == "kept"


# --------------------------------------- api_call_counts diff helper


def test_diff_counts_returns_only_increased_methods() -> None:
    """Per-method delta between two snapshots; only positive increments listed."""
    from tests.calibration.run import _diff_counts

    before = {"search_volumes": 5, "list_issues": 20}
    after = {"search_volumes": 6, "list_issues": 23, "get_issue": 1}
    diff = _diff_counts(before, after)
    # search_volumes: +1, list_issues: +3, get_issue: +1 (was 0).
    assert diff == {"search_volumes": 1, "list_issues": 3, "get_issue": 1}


def test_diff_counts_drops_zero_deltas() -> None:
    """Methods called the same number of times pre and post are omitted."""
    from tests.calibration.run import _diff_counts

    before = {"a": 5, "b": 2}
    after = {"a": 5, "b": 2, "c": 0}
    assert _diff_counts(before, after) == {}


def test_diff_counts_handles_empty_before() -> None:
    """Empty before snapshot (first fixture in a run) → all of after counts."""
    from tests.calibration.run import _diff_counts

    assert _diff_counts({}, {"search_volumes": 1}) == {"search_volumes": 1}


def test_serialize_includes_api_call_counts(tmp_path: Path) -> None:
    """api_call_counts survives the JSON round-trip via _serialize_outcomes."""
    from tests.calibration.run import _serialize_outcomes

    outcome = _outcome(
        api_call_counts={"search_volumes": 1, "list_issues": 7},
    )
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes([outcome], out_path)
    [entry] = json.loads(out_path.read_text())
    assert entry["api_call_counts"] == {"search_volumes": 1, "list_issues": 7}


# --------------------------------------- atomic write + periodic checkpoint


def test_atomic_write_json_leaves_no_temp_file(tmp_path: Path) -> None:
    """After a normal write, no `.tmp` leftover on disk."""
    from tests.calibration.run import _atomic_write_json

    target = tmp_path / "outcomes.json"
    _atomic_write_json(target, [{"file": "/x.cbz"}])
    assert target.exists()
    # No leftover tmp file in the same directory.
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_atomic_write_json_overwrites_existing(tmp_path: Path) -> None:
    """Subsequent writes replace the file content, not append."""
    from tests.calibration.run import _atomic_write_json

    target = tmp_path / "outcomes.json"
    _atomic_write_json(target, [{"k": 1}])
    _atomic_write_json(target, [{"k": 2}])
    assert json.loads(target.read_text()) == [{"k": 2}]


def test_serialize_outcomes_uses_atomic_write(tmp_path: Path) -> None:
    """`_serialize_outcomes` should round-trip even when called twice."""
    from tests.calibration.run import _serialize_outcomes

    target = tmp_path / "outcomes.json"
    _serialize_outcomes([_outcome(score=0.9)], target)
    _serialize_outcomes([_outcome(score=0.8)], target)
    payload = json.loads(target.read_text())
    assert len(payload) == 1
    assert payload[0]["top_score"] == 0.8


def test_calibrate_loop_invokes_checkpoint_every_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `_calibrate_loop` calls the checkpoint callback every Nth fixture.

    Uses a fake source so the loop doesn't hit any real API code paths.
    """
    from tests.calibration.run import _calibrate_loop

    class _NoopSource:
        name = "metron"

        def __init__(self) -> None:
            # Per-instance to satisfy RUF012; matches the production
            # OnlineSource pattern.
            self.api_call_counts: dict[str, int] = {}

        def search(self, profile):
            return []

    # Stub `_score_one` so we don't open Comicbox files — the test is
    # about checkpoint cadence, not about scoring.
    from tests.calibration import run as run_mod

    def _fake_score(source, fixture):
        return _outcome(source=source.name, correct=True)

    monkeypatch.setattr(run_mod, "_score_one", _fake_score)

    # 25 fixtures that "exist" via a real tmp_path/touch dance.
    # We can sidestep the missing-file branch by patching `Path.exists`
    # to always return True.
    monkeypatch.setattr(Path, "exists", lambda self: True)  # noqa: ARG005

    fixtures = [_Fixture(Path(f"/x{i}.cbz"), {"metron": i}, "full") for i in range(25)]
    checkpoints: list[int] = []

    def _capture(outcomes: list) -> None:
        checkpoints.append(len(outcomes))

    _calibrate_loop(
        fixtures,
        [_NoopSource()],  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        checkpoint=_capture,
        checkpoint_every=10,
    )
    # 25 fixtures, checkpoint every 10 → fires at fixture 10 and 20.
    # Fixture 25 doesn't trigger (25 % 10 != 0). Each checkpoint sees
    # the outcomes-so-far count.
    assert checkpoints == [10, 20]


def test_calibrate_loop_skips_checkpoint_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`checkpoint=None` (default) → no callback ever invoked."""
    from tests.calibration import run as run_mod
    from tests.calibration.run import _calibrate_loop

    class _NoopSource:
        name = "metron"

        def __init__(self) -> None:
            # Per-instance to satisfy RUF012; matches the production
            # OnlineSource pattern.
            self.api_call_counts: dict[str, int] = {}

        def search(self, profile):
            return []

    monkeypatch.setattr(
        run_mod,
        "_score_one",
        lambda s, f: _outcome(source=s.name, correct=True),  # noqa: ARG005
    )
    monkeypatch.setattr(Path, "exists", lambda self: True)  # noqa: ARG005

    fixtures = [_Fixture(Path(f"/x{i}.cbz"), {"metron": i}, "full") for i in range(15)]
    # No checkpoint passed; no exception, no callback fires.
    outcomes = _calibrate_loop(
        fixtures,
        [_NoopSource()],  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    assert len(outcomes) == 15


def test_build_checkpoint_labeled_path(tmp_path: Path) -> None:
    """A `label` argument routes to the labeled path."""
    from tests.calibration.run import _build_checkpoint

    fp = tmp_path / "fixtures.json"
    outcomes_path = tmp_path / "fixtures.outcomes.json"
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=outcomes_path,
        label="exhaustive",
        was_filtered=False,
    )
    cp([_outcome(score=0.9)])
    labeled = tmp_path / "fixtures.outcomes.exhaustive.json"
    assert labeled.exists()
    # Canonical path was NOT touched.
    assert not outcomes_path.exists()


def test_build_checkpoint_filtered_uses_merge(tmp_path: Path) -> None:
    """A filtered run's checkpoint goes through the partial-merge path."""
    from tests.calibration.run import _build_checkpoint, _serialize_outcomes

    fp = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    # Seed the partial with an entry that should be preserved.
    _serialize_outcomes(
        [
            _Outcome(
                fixture=_Fixture(Path("/old.cbz"), {"comicvine": 1}, "full"),
                source_name="comicvine",
                top_score=0.0,
                top_issue_id=None,
                top_correct=False,
                n_candidates=0,
            )
        ],
        partial,
    )
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=tmp_path / "fixtures.outcomes.json",
        label=None,
        was_filtered=True,
    )
    cp([_outcome(source="metron", score=0.95, correct=True)])
    payload = json.loads(partial.read_text())
    # Old entry preserved (the merge), new entry added.
    files = {e["file"] for e in payload}
    assert "/old.cbz" in files
    assert "/x.cbz" in files


def test_build_checkpoint_canonical_path(tmp_path: Path) -> None:
    """Non-filtered, non-labeled runs write to canonical outcomes path."""
    from tests.calibration.run import _build_checkpoint

    fp = tmp_path / "fixtures.json"
    outcomes_path = tmp_path / "fixtures.outcomes.json"
    cp = _build_checkpoint(
        fixtures_path=fp,
        outcomes_path=outcomes_path,
        label=None,
        was_filtered=False,
    )
    cp([_outcome(score=0.9)])
    assert outcomes_path.exists()
