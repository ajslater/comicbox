"""
Calibration-harness tests: series dedup, hash-provider gating, retry-path fallback.

Split from test_harness.py to keep per-file maintainability index healthy.
The shared `_outcome` / `_write_outcomes` factories live in
``tests.calibration._harness_helpers``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.calibration._harness_helpers import make_outcome, write_outcomes
from tests.calibration.run import _Fixture

_outcome = make_outcome
_write_outcomes = write_outcomes


# --------------------------------------------- _series_key / --one-per-series


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        pytest.param("Watchmen (1986) #002.cbz", "Watchmen (1986)", id="year-paren"),
        pytest.param("Conan (2004) #005.cbz", "Conan (2004)", id="year-paren-2"),
        pytest.param("Lois Lane (2019) #001.cbz", "Lois Lane (2019)", id="multi-word"),
        pytest.param("Akira (1984) #001.cbz", "Akira (1984)", id="single-word"),
        pytest.param(
            "X-Men Hellfire Gala #001.cbz", "X-Men Hellfire Gala", id="no-paren"
        ),
        # Edge: leading whitespace, multiple spaces
        pytest.param("Foo Bar   #042.cbz", "Foo Bar", id="extra-whitespace"),
        # No issue marker at all → whole filename
        pytest.param("comic.cbz", "comic.cbz", id="no-issue-marker"),
    ],
)
def test_series_key(filename: str, expected: str) -> None:
    from tests.calibration.run import _series_key

    assert _series_key(filename) == expected


def test_dedupe_one_per_series_keeps_first(tmp_path: Path) -> None:
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Watchmen (1986) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Watchmen (1986) #002.cbz", {}, "full"),
        _Fixture(tmp_path / "Watchmen (1986) #003.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #002.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert len(deduped) == 2
    assert deduped[0].file_path.name == "Watchmen (1986) #001.cbz"
    assert deduped[1].file_path.name == "Lois Lane (2019) #001.cbz"


def test_dedupe_one_per_series_distinguishes_volumes(tmp_path: Path) -> None:
    """Lois Lane (1986) and Lois Lane (2019) are separate series — keep both."""
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Lois Lane (1986) #001.cbz", {}, "full"),
        _Fixture(tmp_path / "Lois Lane (2019) #001.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert len(deduped) == 2


def test_dedupe_one_per_series_preserves_input_order(tmp_path: Path) -> None:
    """Iteration order matches input order (not alphabetical or anything)."""
    from tests.calibration.run import _dedupe_one_per_series

    fixtures = [
        _Fixture(tmp_path / "Z Series #001.cbz", {}, "full"),
        _Fixture(tmp_path / "A Series #001.cbz", {}, "full"),
    ]
    deduped = _dedupe_one_per_series(fixtures)
    assert [f.file_path.name for f in deduped] == [
        "Z Series #001.cbz",
        "A Series #001.cbz",
    ]


# --------------------------------------------- _hash_providers / cover-quality gating


class _FakeBox:
    """Minimal stand-in for a Comicbox instance — just enough for _hash_providers."""

    def _local_cover_phash(self) -> str | None:
        return "deadbeef"

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        return f"hash:{url}"


def test_hash_providers_full_returns_methods() -> None:
    """cover_quality='full' wires both providers as callables bound to the box."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "full")
    local, fetcher = _hash_providers(_FakeBox(), fixture)
    # Python creates a fresh bound-method object per attribute access, so
    # `is` comparison won't work — verify behavior instead.
    assert local is not None
    assert fetcher is not None
    assert callable(local)
    assert callable(fetcher)


def test_hash_providers_thumbnail_returns_none() -> None:
    """Slimlib (downscaled-cover) fixtures stay metadata-only."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "thumbnail")
    assert _hash_providers(_FakeBox(), fixture) == (None, None)


def test_hash_providers_missing_returns_none() -> None:
    """Cover-missing fixtures can't contribute to the hash signal."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "missing")
    assert _hash_providers(_FakeBox(), fixture) == (None, None)


def test_hash_providers_call_through_returns_box_results() -> None:
    """The returned callables actually invoke the box's methods."""
    from tests.calibration.run import _hash_providers

    fixture = _Fixture(Path("/x.cbz"), {"metron": 1}, "full")
    local, fetcher = _hash_providers(_FakeBox(), fixture)
    assert local is not None
    assert fetcher is not None
    assert local() == "deadbeef"
    assert fetcher("https://example.test/cover.jpg") == (
        "hash:https://example.test/cover.jpg"
    )


# --------------------------------------- _resolve_retry_outcomes_path fallback


def test_resolve_retry_outcomes_prefers_full(tmp_path: Path) -> None:
    """When both files exist, full takes precedence (canonical source)."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    full = tmp_path / "fixtures.outcomes.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(full, "/a.cbz", "wrong")
    _write_outcomes(partial, "/b.cbz", "wrong")

    assert _resolve_retry_outcomes_path(fixtures_path) == full


def test_resolve_retry_outcomes_falls_back_to_partial(tmp_path: Path) -> None:
    """No full file → use the partial (the user's only iteration data)."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(partial, "/b.cbz", "wrong")

    assert _resolve_retry_outcomes_path(fixtures_path) == partial


def test_resolve_retry_outcomes_raises_when_neither_exists(tmp_path: Path) -> None:
    """Neither file present → clear error naming both expected paths."""
    from tests.calibration.run import _resolve_retry_outcomes_path

    fixtures_path = tmp_path / "fixtures.json"
    with pytest.raises(FileNotFoundError, match=r"outcomes\.partial\.json"):
        _resolve_retry_outcomes_path(fixtures_path)


def test_apply_filters_uses_partial_when_full_missing(tmp_path: Path) -> None:
    """End-to-end: --retry-misses with only a partial file filters as expected."""
    from tests.calibration.run import _apply_filters

    fixtures_path = tmp_path / "fixtures.json"
    partial = tmp_path / "fixtures.outcomes.partial.json"
    _write_outcomes(partial, "/keep.cbz", "wrong")

    fixtures = [
        _Fixture(Path("/keep.cbz"), {"metron": 1}, "full"),
        _Fixture(Path("/drop.cbz"), {"metron": 2}, "full"),
    ]
    out = _apply_filters(
        fixtures,
        fixtures_path=fixtures_path,
        retry_misses=True,
        name_filter=None,
        one_per_series=False,
        limit=None,
    )
    assert [f.file_path.name for f in out] == ["keep.cbz"]


# --------------------------------------- diagnostic detail / cover-score repr


def test_cover_score_repr_fired() -> None:
    """When hashing produced a score, render it as a float."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.91,
        top_cover_score=0.82,
        runner_up_score=0.80,
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "0.82"


def test_cover_score_repr_quality_gated_off() -> None:
    """cover_quality != full → harness never supplied providers."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.91,
        top_cover_score=None,
        hash_providers_supplied=False,
    )
    assert _cover_score_repr(o) == "N/A (cover_quality != full)"


def test_cover_score_repr_unambiguous_metadata() -> None:
    """Wide gap → matcher's _should_invoke_hashing would have skipped."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.97,
        correct=False,
        top_metadata_score=0.97,
        top_cover_score=None,
        runner_up_score=0.50,  # gap = 0.47
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "N/A (unambiguous metadata)"


def test_cover_score_repr_provider_failure() -> None:
    """Tight gap + None cover_score → hashing fired but couldn't produce."""
    from tests.calibration.run import _cover_score_repr

    o = _outcome(
        score=0.89,
        correct=False,
        top_metadata_score=0.89,
        top_cover_score=None,
        runner_up_score=0.85,  # gap = 0.04 < 0.10
        hash_providers_supplied=True,
    )
    assert _cover_score_repr(o) == "N/A (provider returned None)"


def test_print_failed_outcomes_includes_diagnostic_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MISS lines show metadata=, cover=, gap= for hand-investigation."""
    from tests.calibration.run import _print_failed_outcomes

    outcomes = [
        _outcome(
            source="comicvine",
            score=0.89,
            correct=False,
            n=9,
            top_metadata_score=0.91,
            top_cover_score=0.82,
            runner_up_score=0.80,
            hash_providers_supplied=True,
        ),
    ]
    _print_failed_outcomes(outcomes)
    out = capsys.readouterr().out
    assert "[MISS] comicvine" in out
    assert "metadata=0.91" in out
    assert "cover=0.82" in out
    assert "gap=0.09" in out  # 0.89 - 0.80


def test_print_failed_outcomes_handles_empty_n(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """EMPTY (n=0) lines don't crash trying to format missing diagnostic fields."""
    from tests.calibration.run import _print_failed_outcomes

    outcomes = [_outcome(correct=None, n=0)]  # no diagnostic fields set
    _print_failed_outcomes(outcomes)
    out = capsys.readouterr().out
    assert "[EMPTY]" in out
    # No diagnostic line for empty cases (top_metadata_score is None).
    assert "metadata=" not in out


def test_print_progress_distinguishes_empty_from_no_expected_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Used to be one conflated message; split for clarity."""
    from tests.calibration.run import _print_progress

    fixture = _Fixture(Path("/x.cbz"), {}, "full")  # no expected ids
    # Case 1: actually returned 0 candidates.
    empty = _outcome(correct=None, n=0)
    # Case 2: 5 candidates returned but fixture has no labeled id.
    no_id = _outcome(correct=None, n=5)

    _print_progress(empty, fixture)
    _print_progress(no_id, fixture)
    out = capsys.readouterr().out

    assert "no candidates returned" in out
    assert "no expected metron id" in out
    assert "n=5" in out


def test_serialize_includes_diagnostic_fields(tmp_path: Path) -> None:
    """Outcomes JSON carries metadata/cover/gap info for post-hoc analysis."""
    from tests.calibration.run import _serialize_outcomes

    outcomes = [
        _outcome(
            source="comicvine",
            score=0.89,
            correct=False,
            top_metadata_score=0.91,
            top_cover_score=0.82,
            runner_up_score=0.80,
            hash_providers_supplied=True,
        ),
    ]
    out_path = tmp_path / "outcomes.json"
    _serialize_outcomes(outcomes, out_path)
    payload = json.loads(out_path.read_text())
    [entry] = payload
    assert entry["top_metadata_score"] == 0.91
    assert entry["top_cover_score"] == 0.82
    assert entry["runner_up_score"] == 0.80
    assert entry["hash_providers_supplied"] is True
