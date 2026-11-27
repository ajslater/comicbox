"""Ending a `-j N` run: Ctrl-C and abort stop the batch, not just one file."""

from __future__ import annotations

import threading
import time
from argparse import Namespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online import retry
from comicbox.run import Runner

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_BATCH = 20


def _runner(tmp_path: Path, count: int = _BATCH, jobs: int = 2) -> Runner:
    paths = []
    for i in range(count):
        path = tmp_path / f"file_{i:02}.cbz"
        path.write_bytes(b"")
        paths.append(str(path))
    return Runner(
        Namespace(comicbox=Namespace(paths=paths, general=Namespace(jobs=jobs)))
    )


def _interrupting_run_on_file(seen: list[Path], exc: BaseException):
    """Record each file, raise `exc` on the second, and pace the rest."""
    lock = threading.Lock()

    def run_on_file(_self: Runner, path: Path) -> None:
        with lock:
            seen.append(path)
            count = len(seen)
        if count == 2:
            raise exc
        time.sleep(0.05)

    return run_on_file


def test_keyboard_interrupt_drops_the_queued_files(tmp_path: Path) -> None:
    """
    Ctrl-C ends the batch: the files still queued are never started.

    The pool's context exit joined every queued file before the
    interrupt surfaced, so a Ctrl-C under -j N processed the whole run.
    """
    runner = _runner(tmp_path)
    seen: list[Path] = []
    fake = _interrupting_run_on_file(seen, KeyboardInterrupt())
    with patch.object(Runner, "run_on_file", fake), pytest.raises(KeyboardInterrupt):
        runner.run()
    # The interrupting file, the one in flight beside it, and at most one
    # more each worker took before the main thread saw the interrupt.
    assert len(seen) <= 4


# ------------------------------------- abort wakes in-flight retry sleeps


@pytest.fixture(autouse=True)
def _clear_retry_cancel() -> Iterator[None]:
    """Leave the process-wide retry cancel signal as each test found it."""
    retry.clear_cancel()
    yield
    retry.clear_cancel()


class _RateLimitedError(Exception):
    """A rate-limit refusal whose server hint asks for a long wait."""

    retry_after = 5.0


class _RateLimitedSource:
    """A source whose every call is refused for its rate limit."""

    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def classify_retry_exception(_exc: BaseException) -> retry.RetryCategory:
        return retry.RetryCategory.RATE_LIMIT

    @retry.with_retry()
    def fetch(self) -> None:
        self.calls += 1
        raise _RateLimitedError


def _retry_then_end(source: _RateLimitedSource, exc: BaseException):
    """One file waits out its rate limit; the other ends the run with `exc`."""

    def run_on_file(_self: Runner, path: Path) -> None:
        if path.name == "file_00.cbz":
            source.fetch()
        time.sleep(0.1)
        raise exc

    return run_on_file


@pytest.mark.parametrize(
    "exc",
    [OnlineLookupAbortedError("aborted at the prompt"), KeyboardInterrupt()],
    ids=["abort", "ctrl-c"],
)
def test_ending_a_run_wakes_retry_sleeps(tmp_path: Path, exc: BaseException) -> None:
    """
    An abort or Ctrl-C under -j N does not wait out a sibling's retry sleep.

    The process-wide cancel signal was never set, so the pool's join sat
    through every in-flight rate-limit wait, up to an hour each.
    """
    runner = _runner(tmp_path, count=2)
    source = _RateLimitedSource()
    fake = _retry_then_end(source, exc)
    start = time.monotonic()
    with patch.object(Runner, "run_on_file", fake), pytest.raises(type(exc)):
        runner.run()
    assert time.monotonic() - start < 2
    assert source.calls == 1


def test_a_run_starts_with_retries_allowed(tmp_path: Path) -> None:
    """A cancel left over from an earlier run does not abort the next one."""
    retry.request_cancel()
    cancelled: list[bool] = []
    runner = _runner(tmp_path, count=1, jobs=1)
    with patch.object(
        Runner,
        "run_on_file",
        lambda _self, _path: cancelled.append(retry.is_cancelled()),
    ):
        runner.run()
    assert cancelled == [False]
