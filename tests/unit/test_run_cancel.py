"""Ending a `-j N` run: Ctrl-C and abort stop the batch, not just one file."""

from __future__ import annotations

import threading
import time
from argparse import Namespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from comicbox.run import Runner

if TYPE_CHECKING:
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
