"""Runner parallel-batch tests (M7)."""

from __future__ import annotations

import threading
from argparse import Namespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from comicbox.run import Runner

if TYPE_CHECKING:
    from pathlib import Path


def _make_paths(tmp_path: Path, count: int) -> list[str]:
    paths = []
    for i in range(count):
        p = tmp_path / f"file_{i}.cbz"
        p.write_bytes(b"")  # zero-byte cbz; Comicbox will fail to open it
        paths.append(str(p))
    return paths


def test_jobs_default_is_one(tmp_path: Path) -> None:
    """Default config keeps the single-threaded path."""
    paths = _make_paths(tmp_path, 1)
    runner = Runner(Namespace(comicbox=Namespace(paths=paths, print_metadata=True)))
    assert runner._config.jobs == 1


def test_jobs_setting_threadpool_invocation(tmp_path: Path) -> None:
    """Jobs > 1 routes the run through ThreadPoolExecutor."""
    paths = _make_paths(tmp_path, 4)
    runner = Runner(
        Namespace(
            comicbox=Namespace(paths=paths, jobs=2, print_metadata=True)
        )
    )

    called_paths: list[Path] = []

    def fake_run_one(self, path):
        called_paths.append(path)

    with patch.object(Runner, "_run_one", fake_run_one):
        runner.run()

    # All four paths processed, regardless of order.
    assert sorted(p.name for p in called_paths) == [
        f"file_{i}.cbz" for i in range(4)
    ]


def test_single_job_takes_serial_path(tmp_path: Path) -> None:
    """jobs=1 uses run_on_file (preserves original control flow incl. recurse)."""
    paths = _make_paths(tmp_path, 2)
    runner = Runner(Namespace(comicbox=Namespace(paths=paths, jobs=1)))
    seen: list[str] = []

    def fake_run_on_file(self, path):
        seen.append(str(path))

    with patch.object(Runner, "run_on_file", fake_run_on_file):
        runner.run()

    assert seen == paths  # original order preserved on the serial path


def test_jobs_clamped_to_minimum_one() -> None:
    """jobs=0 or negative collapses to serial."""
    cfg = Runner(Namespace(comicbox=Namespace(jobs=0)))._config
    assert cfg.jobs == 1


# ---------------------------------------------- prompt-lock concurrency


def test_prompt_lock_serializes_concurrent_callers() -> None:
    """At most one selector runs at a time across the process."""
    from concurrent.futures import ThreadPoolExecutor

    from comicbox.box.online_lookup import ComicboxOnlineLookup

    enter_count = 0
    max_concurrent = 0
    lock = threading.Lock()

    def selector_body() -> None:
        nonlocal enter_count, max_concurrent
        with lock:
            enter_count += 1
            max_concurrent = max(max_concurrent, enter_count)
        threading.Event().wait(0.05)
        with lock:
            enter_count -= 1

    def worker() -> None:
        # Use the same lock comicbox does (class-level).
        with ComicboxOnlineLookup._PROMPT_LOCK:
            selector_body()

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(worker) for _ in range(8)]
        for f in futures:
            f.result()

    # If the lock works, max_concurrent should be 1 — never two threads in
    # the selector body at the same time.
    assert max_concurrent == 1
