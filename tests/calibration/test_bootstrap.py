"""Unit tests for the calibration fixture bootstrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.calibration.bootstrap import (
    _build_fixture,
    _coerce_int,
    _should_keep,
    iter_comics,
)

# --------------------------------------------------------- _coerce_int


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="none"),
        pytest.param(42, 42, id="int"),
        pytest.param("42", 42, id="str-numeric"),
        pytest.param("  42 ", 42, id="str-whitespace"),
        # CV-style prefixed key — leave to the run-harness's parser.
        pytest.param("4000-12345", None, id="str-prefixed"),
        pytest.param("abc", None, id="str-alpha"),
        pytest.param("", None, id="str-empty"),
    ],
)
def test_coerce_int(raw: object, expected: int | None) -> None:
    assert _coerce_int(raw) == expected


# --------------------------------------------------------- _should_keep


@pytest.mark.parametrize(
    ("metron", "cv", "require_both", "kept"),
    [
        # No ids at all — never kept.
        (None, None, False, False),
        (None, None, True, False),
        # One id (default mode keeps it).
        (1, None, False, True),
        (None, 1, False, True),
        # One id with --require-both: dropped.
        (1, None, True, False),
        (None, 1, True, False),
        # Both ids — always kept.
        (1, 2, False, True),
        (1, 2, True, True),
    ],
)
def test_should_keep(
    metron: int | None, cv: int | None, *, require_both: bool, kept: bool
) -> None:
    assert _should_keep(metron, cv, require_both=require_both) is kept


# --------------------------------------------------------- iter_comics


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def test_iter_comics_walks_dirs_recursively(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a.cbz")
    b = _touch(tmp_path / "sub" / "b.cbr")
    c = _touch(tmp_path / "sub" / "deep" / "c.pdf")
    _touch(tmp_path / "ignored.txt")
    found = list(iter_comics([tmp_path]))
    assert sorted(found) == sorted([a, b, c])


def test_iter_comics_accepts_individual_files(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a.cbz")
    b = _touch(tmp_path / "b.cbr")
    found = list(iter_comics([a, b]))
    assert sorted(found) == sorted([a, b])


def test_iter_comics_dedupes_across_paths(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a.cbz")
    # Pass the dir AND the file directly — should appear once.
    found = list(iter_comics([tmp_path, a]))
    assert found.count(a) == 1


def test_iter_comics_filters_by_suffix(tmp_path: Path) -> None:
    _touch(tmp_path / "fake.txt")
    _touch(tmp_path / "fake.json")
    real = _touch(tmp_path / "real.cbz")
    found = list(iter_comics([tmp_path]))
    assert found == [real]


def test_iter_comics_handles_missing_path(tmp_path: Path) -> None:
    # Doesn't exist — should warn but not crash.
    found = list(iter_comics([tmp_path / "no_such_dir"]))
    assert found == []


def test_iter_comics_expands_tilde() -> None:
    # ~/non-existent-test-dir-comicbox-bootstrap/ shouldn't crash.
    list(iter_comics([Path("~/non-existent-test-dir-comicbox-bootstrap")]))


# --------------------------------------------------------- _build_fixture


def test_build_fixture_includes_all_fields() -> None:
    f = _build_fixture(Path("/x/y.cbz"), 42, 99, "thumbnail")
    assert f == {
        "file": "/x/y.cbz",
        "metron": 42,
        "comicvine": 99,
        "cover_quality": "thumbnail",
    }


def test_build_fixture_keeps_none_ids() -> None:
    """JSON null is meaningful — preserves 'this comic isn't in DB X'."""
    f = _build_fixture(Path("/x.cbz"), None, 99, "full")
    assert f["metron"] is None
    assert f["comicvine"] == 99
