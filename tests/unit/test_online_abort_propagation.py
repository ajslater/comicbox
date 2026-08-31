"""
``OnlineLookupAbortedError`` must end the run, everywhere.

Abort is not a per-file or per-API-call failure: the user answered
"abort" at a prompt, or a caller cancelled a retry sleep. Four broad
``except Exception`` handlers degraded it into "log it and carry on", so
a ``--recurse`` walk kept prompting for the rest of the library and a
cancelled source call fell through to the next search attempt.

``OnlineSource.lookup_issue`` (formats/base/online/sources/base.py) has
always had the right shape -- re-raise the abort above the broad handler
-- and these are the sites that didn't.
"""

from __future__ import annotations

import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from comicbox.config.settings import (
    OnlineSettings,
    OnlineSourceCredentials,
)
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.run import Runner

_ABORT_REASON = "online: aborted by user from prompt"

# The fakes below never touch the session; the sources' signatures are
# vendor-typed (mokkari Session), so hand them an untyped placeholder.
_NO_SESSION: Any = None


def _abort() -> OnlineLookupAbortedError:
    return OnlineLookupAbortedError(_ABORT_REASON)


# --- Runner: --recurse ------------------------------------------------------


def _make_comics(tmp_path: Path, count: int) -> list[Path]:
    paths = []
    for i in range(count):
        path = tmp_path / f"comic_{i:02d}.cbz"
        path.write_bytes(b"")
        paths.append(path)
    return paths


def _runner(tmp_path: Path, **general: Any) -> Runner:
    return Runner(
        Namespace(
            comicbox=Namespace(
                paths=[str(tmp_path)],
                general=Namespace(recurse=True, **general),
            )
        )
    )


def test_recurse_stops_the_walk_on_abort(tmp_path, monkeypatch) -> None:
    """An abort on file 2 must not leave files 3..N to be prompted for."""
    _make_comics(tmp_path, 5)
    seen: list[str] = []

    def fake_run_on_file(self, path):
        seen.append(Path(path).name)
        if len(seen) == 2:
            raise _abort()

    monkeypatch.setattr(Runner, "run_on_file", fake_run_on_file)
    runner = _runner(tmp_path)

    with pytest.raises(OnlineLookupAbortedError):
        runner.recurse(tmp_path)

    assert seen == ["comic_00.cbz", "comic_01.cbz"]


def test_recurse_still_swallows_ordinary_file_errors(tmp_path, monkeypatch) -> None:
    """Batch resilience is intact: a broken comic doesn't end the walk."""
    _make_comics(tmp_path, 4)
    seen: list[str] = []

    def fake_run_on_file(self, path):
        seen.append(Path(path).name)
        if len(seen) == 2:
            msg = "corrupt archive"
            raise ValueError(msg)

    monkeypatch.setattr(Runner, "run_on_file", fake_run_on_file)
    runner = _runner(tmp_path)

    runner.recurse(tmp_path)

    assert len(seen) == 4


# --- Runner: _run_one -------------------------------------------------------


def test_run_one_reraises_abort(tmp_path, monkeypatch) -> None:
    """The per-file guard is where both batch paths pick the abort up."""
    path = _make_comics(tmp_path, 1)[0]
    runner = _runner(tmp_path)

    class _AbortingBox:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def print_file_header(self) -> None:
            pass

        def run(self) -> None:
            raise _abort()

    monkeypatch.setattr("comicbox.run.Comicbox", _AbortingBox)

    with pytest.raises(OnlineLookupAbortedError):
        runner._run_one(path)


def test_run_one_still_swallows_ordinary_errors(tmp_path, monkeypatch) -> None:
    """A zero-byte cbz still fails softly, as batch resilience requires."""
    path = _make_comics(tmp_path, 1)[0]
    runner = _runner(tmp_path)

    runner._run_one(path)  # must not raise


# --- Runner: -j N -----------------------------------------------------------


def test_parallel_run_aborts_and_drops_queued_files(tmp_path, monkeypatch) -> None:
    """
    Abort ends the batch instead of working through the remaining paths.

    Files already in flight can't be interrupted from the collector, but
    everything still queued is cancelled, so the count of processed files
    stays near the worker count rather than the whole batch.
    """
    paths = _make_comics(tmp_path, 40)
    started: list[Path] = []

    def fake_run_one(self, path):
        started.append(path)
        if path == paths[0]:
            raise _abort()
        # Keep the workers busy so the pool can't drain the queue before
        # the collector sees the abort and cancels what's left.
        time.sleep(0.05)

    monkeypatch.setattr(Runner, "_run_one", fake_run_one)
    runner = _runner(tmp_path, jobs=2)

    with pytest.raises(OnlineLookupAbortedError):
        runner._run_parallel(paths, 2)

    assert len(started) < len(paths)


def test_parallel_run_still_swallows_ordinary_errors(tmp_path, monkeypatch) -> None:
    """One bad comic must not take the rest of the batch down with it."""
    paths = _make_comics(tmp_path, 6)
    started: list[Path] = []

    def fake_run_one(self, path):
        started.append(path)
        if path == paths[0]:
            msg = "corrupt archive"
            raise ValueError(msg)

    monkeypatch.setattr(Runner, "_run_one", fake_run_one)
    runner = _runner(tmp_path, jobs=2)

    runner._run_parallel(paths, 2)

    assert len(started) == len(paths)


# --- ComicVine: the per-volume issue-list loop ------------------------------


class _FakeVolume:
    """Minimal simyan BasicVolume stand-in that clears both pre-filters."""

    id = 77
    name = "Foo Comics"
    start_year = 2018
    aliases = None


def _cv_source() -> ComicVineOnlineSource:
    return ComicVineOnlineSource(OnlineSourceCredentials(key="x"), OnlineSettings())


def _cv_profile() -> ComicProfile:
    return ComicProfile(series="Foo Comics", issue="5", year=2020)


def test_comicvine_per_volume_loop_propagates_abort(monkeypatch) -> None:
    """A cancelled retry sleep inside one volume aborts the whole search."""
    src = _cv_source()

    def boom(*args, **kwargs):
        raise _abort()

    monkeypatch.setattr(src, "_list_with_year_retry", boom)

    with pytest.raises(OnlineLookupAbortedError):
        src._candidates_for_volume(
            _NO_SESSION,
            _FakeVolume(),
            profile=_cv_profile(),
            issue_number="5",
            year=2020,
            name_threshold=0.0,
        )


def test_comicvine_per_volume_loop_still_degrades_on_api_error(monkeypatch) -> None:
    """An ordinary source-side failure still drops just that volume."""
    src = _cv_source()

    def boom(*args, **kwargs):
        msg = "comicvine 500"
        raise RuntimeError(msg)

    monkeypatch.setattr(src, "_list_with_year_retry", boom)

    assert (
        src._candidates_for_volume(
            _NO_SESSION,
            _FakeVolume(),
            profile=_cv_profile(),
            issue_number="5",
            year=2020,
            name_threshold=0.0,
        )
        == []
    )


# --- Metron: the ±1 year-retry loop -----------------------------------------


def _metron_source() -> MetronOnlineSource:
    return MetronOnlineSource(
        OnlineSourceCredentials(user="u", password="p"), OnlineSettings()
    )


def _metron_profile() -> ComicProfile:
    return ComicProfile(series="Foo Comics", issue="5", year=2020)


def test_metron_year_retry_loop_propagates_abort(monkeypatch) -> None:
    """The Y-1 retry must not swallow an abort to give Y+1 a turn."""
    src = _metron_source()
    calls: list[int | None] = []

    def fake_fetch(session, profile, *, cover_year_override, include_volume):
        calls.append(cover_year_override)
        if cover_year_override is None:
            return []  # year-exact miss → the retry cascade runs
        raise _abort()

    monkeypatch.setattr(src, "_fetch_candidates_by_name", fake_fetch)

    with pytest.raises(OnlineLookupAbortedError):
        src._search_with_year_retry(_NO_SESSION, _metron_profile(), include_volume=True)

    # Aborted on the first retry; Y+1 never got its turn.
    assert calls == [None, 2019]


def test_metron_year_retry_loop_still_tries_the_sibling_year(monkeypatch) -> None:
    """An ordinary retry failure still lets the other ±1 year run."""
    src = _metron_source()
    calls: list[int | None] = []

    def fake_fetch(session, profile, *, cover_year_override, include_volume):
        calls.append(cover_year_override)
        if cover_year_override == 2019:
            msg = "metron 500"
            raise RuntimeError(msg)
        return []

    monkeypatch.setattr(src, "_fetch_candidates_by_name", fake_fetch)

    assert (
        src._search_with_year_retry(_NO_SESSION, _metron_profile(), include_volume=True)
        == []
    )
    assert calls == [None, 2019, 2021]
