"""
Unit tests for the Metron labeler's pure-Python helpers.

The live `_build_metron_session` and `lookup_metron_by_cv_id` paths need
real Metron credentials, so they're exercised by the calibration runs
themselves. These tests cover the surrounding logic: iteration, idempotent
re-runs, atomic writes, and stats accounting.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.calibration.label_metron import (
    _atomic_write_fixtures,
    _iter_labelable,
    _LabelStats,
    label_fixtures,
    lookup_metron_by_cv_id,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    import pytest


# --- _iter_labelable ---


def test_iter_labelable_picks_cv_only_fixtures() -> None:
    fixtures = [
        {"file": "/a.cbz", "metron": None, "comicvine": 100},
        {"file": "/b.cbz", "metron": 50, "comicvine": 200},
        {"file": "/c.cbz", "metron": None, "comicvine": 300},
        {"file": "/d.cbz", "metron": None, "comicvine": None},
    ]
    out = list(_iter_labelable(fixtures))
    # Only /a and /c qualify (cv id + no metron id).
    assert [i for i, _ in out] == [0, 2]


def test_iter_labelable_skips_when_metron_already_set() -> None:
    """Idempotent re-runs: fixtures that already have metron ids are skipped."""
    fixtures = [{"file": "/x.cbz", "metron": 42, "comicvine": 100}]
    assert list(_iter_labelable(fixtures)) == []


def test_iter_labelable_skips_when_no_cv_id() -> None:
    """A fixture with neither id is unreachable — nothing to cross-reference."""
    fixtures = [{"file": "/x.cbz", "metron": None, "comicvine": None}]
    assert list(_iter_labelable(fixtures)) == []


def test_iter_labelable_empty_input() -> None:
    assert list(_iter_labelable([])) == []


# --- _atomic_write_fixtures ---


def test_atomic_write_creates_valid_json(tmp_path: Path) -> None:
    fixtures = [{"file": "/a.cbz", "metron": 1, "comicvine": 2}]
    path = tmp_path / "fixtures.json"
    _atomic_write_fixtures(path, fixtures)
    assert json.loads(path.read_text()) == fixtures


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps([{"file": "/old.cbz"}]))
    _atomic_write_fixtures(path, [{"file": "/new.cbz"}])
    # Old contents are replaced wholesale.
    assert json.loads(path.read_text()) == [{"file": "/new.cbz"}]


def test_atomic_write_does_not_leave_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "fixtures.json"
    _atomic_write_fixtures(path, [{"file": "/a.cbz"}])
    # No `.tmp` sibling remains after a successful write.
    assert not (tmp_path / "fixtures.json.tmp").exists()


# --- label_fixtures (with mocked session) ---


class _FakeIssue:
    """Just-enough mokkari issue surface for the labeler."""

    def __init__(self, issue_id: int) -> None:
        self.id = issue_id


class _FakeSession:
    """
    Captures cv_id lookups and replays a canned mapping.

    Lets us drive `label_fixtures` end-to-end against tmp_path without
    hitting Metron. Records every cv_id queried so tests can assert on
    the call pattern.
    """

    def __init__(self, mapping: dict[int, int]) -> None:
        self._mapping = mapping
        self.calls: list[int] = []

    def issues_list(self, params: dict[str, int]) -> Iterable[_FakeIssue]:
        cv_id = int(params["cv_id"])
        self.calls.append(cv_id)
        if cv_id in self._mapping:
            return [_FakeIssue(self._mapping[cv_id])]
        return []


def _write_fixtures(tmp_path: Path, fixtures: list[dict]) -> Path:
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(fixtures))
    return path


def test_label_fixtures_writes_back_new_metron_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: CV-only fixtures get Metron ids written back."""
    fixtures = [
        {"file": "/a.cbz", "metron": None, "comicvine": 100},
        {"file": "/b.cbz", "metron": None, "comicvine": 200},
    ]
    path = _write_fixtures(tmp_path, fixtures)
    fake = _FakeSession({100: 500, 200: 600})
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: fake,
    )

    stats = label_fixtures(path)
    assert stats.labeled == 2
    assert stats.not_found == 0
    written = json.loads(path.read_text())
    assert written[0]["metron"] == 500
    assert written[1]["metron"] == 600


def test_label_fixtures_leaves_metron_null_when_no_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metron returning nothing → metron stays null, not_found counter ticks."""
    fixtures = [{"file": "/a.cbz", "metron": None, "comicvine": 999}]
    path = _write_fixtures(tmp_path, fixtures)
    fake = _FakeSession({})  # nothing on Metron
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: fake,
    )

    stats = label_fixtures(path)
    assert stats.labeled == 0
    assert stats.not_found == 1
    assert json.loads(path.read_text())[0]["metron"] is None


def test_label_fixtures_preserves_existing_metron_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotent re-run: don't re-query, don't clobber pre-existing ids."""
    fixtures = [
        {"file": "/a.cbz", "metron": 42, "comicvine": 100},
        {"file": "/b.cbz", "metron": None, "comicvine": 200},
    ]
    path = _write_fixtures(tmp_path, fixtures)
    fake = _FakeSession({100: 9999, 200: 600})  # 100 would clobber if queried
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: fake,
    )

    stats = label_fixtures(path)
    # Only the CV-only fixture got queried; the pre-labeled one was skipped.
    assert fake.calls == [200]
    assert stats.labeled == 1
    assert stats.already_labeled == 1
    written = json.loads(path.read_text())
    assert written[0]["metron"] == 42  # untouched
    assert written[1]["metron"] == 600  # newly labeled


def test_label_fixtures_dry_run_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--dry-run` reports what would change but leaves the file alone."""
    fixtures = [{"file": "/a.cbz", "metron": None, "comicvine": 100}]
    path = _write_fixtures(tmp_path, fixtures)
    fake = _FakeSession({100: 500})
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: fake,
    )

    label_fixtures(path, dry_run=True)
    # The fake session still got queried (so the user can preview cost),
    # but the file is unchanged.
    assert fake.calls == [100]
    assert json.loads(path.read_text())[0]["metron"] is None


def test_label_fixtures_respects_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--limit N` stops after N lookups (chunked / smoke-test mode)."""
    fixtures = [
        {"file": f"/{i}.cbz", "metron": None, "comicvine": 100 + i} for i in range(10)
    ]
    path = _write_fixtures(tmp_path, fixtures)
    fake = _FakeSession({100 + i: 500 + i for i in range(10)})
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: fake,
    )

    label_fixtures(path, limit=3)
    assert len(fake.calls) == 3


def test_label_fixtures_handles_non_retriable_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A non-retriable Metron error on one fixture doesn't abort the run.

    Uses `ValueError` which is in `_NON_RETRIABLE` — the retry decorator
    passes it straight through, the outer except catches it, the fixture
    is marked no-coverage, and the loop continues to the next fixture.
    """

    class _FlakySession:
        def __init__(self) -> None:
            self.calls = 0

        def issues_list(self, params: dict[str, int]) -> list[_FakeIssue]:
            self.calls += 1
            if self.calls == 1:
                msg = "bad request param"
                raise ValueError(msg)
            return [_FakeIssue(500)]

    fixtures = [
        {"file": "/a.cbz", "metron": None, "comicvine": 100},
        {"file": "/b.cbz", "metron": None, "comicvine": 200},
    ]
    path = _write_fixtures(tmp_path, fixtures)
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        _FlakySession,
    )

    stats = label_fixtures(path)
    # First call errored (→ not_found), second succeeded.
    assert stats.not_found == 1
    assert stats.labeled == 1


def test_label_fixtures_retries_rate_limit_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A `RateLimitError` triggers @with_retry's auto-retry with the server hint.

    Before this fix, Metron's 20/min cap would silently mark CVids as
    "no metron coverage" whenever rate-limiting kicked in (false
    negative on the calibration ground truth). The retry decorator now
    catches RateLimitError, honors `retry_after`, and replays.
    """

    # Mokkari-shaped exception: the retry decorator keys on the type's
    # name string "RateLimitError" and on `retry_after`.
    class RateLimitError(Exception):
        def __init__(self, retry_after: float) -> None:
            super().__init__("Rate limit exceeded")
            self.retry_after = retry_after

    class _RateLimitedSession:
        def __init__(self) -> None:
            self.calls = 0

        def issues_list(self, params: dict[str, int]) -> list[_FakeIssue]:
            self.calls += 1
            if self.calls == 1:
                # Tiny retry_after so the test runs fast — the decorator
                # honors the server hint over its default schedule.
                raise RateLimitError(retry_after=0.001)
            return [_FakeIssue(500)]

    fixtures = [{"file": "/a.cbz", "metron": None, "comicvine": 100}]
    path = _write_fixtures(tmp_path, fixtures)
    session_instance = _RateLimitedSession()
    monkeypatch.setattr(
        "tests.calibration.label_metron._build_metron_session",
        lambda: session_instance,
    )

    stats = label_fixtures(path)
    # The rate-limited first call was retried, the retry succeeded.
    assert session_instance.calls == 2
    assert stats.labeled == 1
    assert stats.not_found == 0
    assert json.loads(path.read_text())[0]["metron"] == 500


def test_label_fixtures_writes_incrementally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Each successful lookup persists immediately — Ctrl-C-safe runs.

    Use a fake session that raises after the second call. The first
    call's result must already be on disk before the second call
    starts.
    """
    on_disk_after_calls: dict[int, list[dict]] = {}

    class _Spy:
        def __init__(self) -> None:
            self.calls = 0

        def issues_list(self, params: dict[str, int]) -> list[_FakeIssue]:
            self.calls += 1
            if self.calls == 1:
                # First call returns a hit.
                return [_FakeIssue(500)]
            # Snapshot the file before raising, so the test can verify
            # the first call's result was already persisted.
            on_disk_after_calls[self.calls] = json.loads(path.read_text())
            # ValueError is in _NON_RETRIABLE so the decorator passes
            # it straight through — keeps the test fast (no retry sleep).
            msg = "synthetic post-first-call failure"
            raise ValueError(msg)

    fixtures = [
        {"file": "/a.cbz", "metron": None, "comicvine": 100},
        {"file": "/b.cbz", "metron": None, "comicvine": 200},
    ]
    path = _write_fixtures(tmp_path, fixtures)
    monkeypatch.setattr("tests.calibration.label_metron._build_metron_session", _Spy)

    label_fixtures(path)
    # Before the second call's exception, /a's metron was already on disk.
    assert on_disk_after_calls[2][0]["metron"] == 500


# --- lookup_metron_by_cv_id ---


def test_lookup_metron_by_cv_id_returns_int_id_on_hit() -> None:
    session = _FakeSession({100: 500})
    assert lookup_metron_by_cv_id(session, 100) == 500  # type: ignore[arg-type]


def test_lookup_metron_by_cv_id_returns_none_on_empty_result() -> None:
    session = _FakeSession({})
    assert lookup_metron_by_cv_id(session, 999) is None  # type: ignore[arg-type]


def test_lookup_metron_by_cv_id_returns_first_on_ambiguous(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Multi-hit responses log a warning but still return the first id."""

    class _MultiHitSession:
        def issues_list(self, params: dict[str, int]) -> list[_FakeIssue]:
            return [_FakeIssue(700), _FakeIssue(800)]

    result = lookup_metron_by_cv_id(_MultiHitSession(), 100)  # type: ignore[arg-type]
    assert result == 700
    captured = capsys.readouterr()
    assert "matched 2 Metron issues" in captured.err


def test_lookup_metron_by_cv_id_swallows_non_retriable_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Non-retriable errors log and return None, not propagate.

    Uses `ValueError` (in `_NON_RETRIABLE` per `comicbox.formats.base.online.retry`) so
    `@with_retry()` passes it straight through without a 31s exponential
    backoff. Retriable errors (RateLimitError, RuntimeError, etc.) get
    the retry path — see `test_label_fixtures_retries_rate_limit_then_succeeds`.
    """

    class _BrokenSession:
        def issues_list(self, params: dict[str, int]) -> list[_FakeIssue]:
            msg = "bad param"
            raise ValueError(msg)

    assert lookup_metron_by_cv_id(_BrokenSession(), 100) is None  # type: ignore[arg-type]
    assert "Metron lookup failed" in capsys.readouterr().err


# --- _LabelStats ---


def test_label_stats_default_zeroed() -> None:
    stats = _LabelStats()
    assert stats.total == 0
    assert stats.labeled == 0
    assert stats.not_found == 0
    assert stats.already_labeled == 0
    assert stats.skipped_no_cv == 0
    assert stats.errored == 0
