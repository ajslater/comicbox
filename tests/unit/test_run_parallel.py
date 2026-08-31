"""Runner parallel-batch tests (M7)."""

from __future__ import annotations

import shutil
import threading
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from loguru import logger as loguru_logger

from comicbox.config import get_config
from comicbox.config.settings import (
    ComicboxSettings,
    OnlineAuthSettings,
    OnlineSourceCredentials,
)
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.formats.base.online.rate_limits import METRON_DEFAULT_PER_MINUTE
from comicbox.run import Runner
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Generator


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
    runner = Runner(
        Namespace(comicbox=Namespace(paths=paths, print=Namespace(phases="p")))
    )
    assert runner._config.general.jobs == 1


def test_jobs_setting_threadpool_invocation(tmp_path: Path) -> None:
    """Jobs > 1 routes the run through ThreadPoolExecutor."""
    paths = _make_paths(tmp_path, 4)
    runner = Runner(
        Namespace(
            comicbox=Namespace(
                paths=paths,
                general=Namespace(jobs=2),
                print=Namespace(phases="p"),
            )
        )
    )

    called_paths: list[Path] = []

    def fake_run_one(self, path):
        called_paths.append(path)

    with patch.object(Runner, "_run_one", fake_run_one):
        runner.run()

    # All four paths processed, regardless of order.
    assert sorted(p.name for p in called_paths) == [f"file_{i}.cbz" for i in range(4)]


def test_single_job_takes_serial_path(tmp_path: Path) -> None:
    """jobs=1 uses run_on_file (preserves original control flow incl. recurse)."""
    paths = _make_paths(tmp_path, 2)
    runner = Runner(
        Namespace(comicbox=Namespace(paths=paths, general=Namespace(jobs=1)))
    )
    seen: list[str] = []

    def fake_run_on_file(self, path):
        seen.append(str(path))

    with patch.object(Runner, "run_on_file", fake_run_on_file):
        runner.run()

    assert seen == paths  # original order preserved on the serial path


def test_jobs_clamped_to_minimum_one() -> None:
    """jobs=0 or negative collapses to serial."""
    cfg = Runner(Namespace(comicbox=Namespace(general=Namespace(jobs=0))))._config
    assert cfg.general.jobs == 1


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


# ------------------------------------------------ metron thread-pool cap


def _metron_settings(
    *,
    enabled: bool = True,
    sources: tuple[str, ...] | None = None,
    user: str | None = "u",
    password: str | None = "p",  # noqa: S107
    key: str | None = None,
) -> ComicboxSettings:
    """Prebuilt settings exercising every `_metron_is_active` input."""
    cfg = get_config(Namespace(comicbox=Namespace()))
    lookup = replace(cfg.online.lookup, enabled=enabled, sources=sources)
    creds = {"metron": OnlineSourceCredentials(user=user, password=password, key=key)}
    online = replace(cfg.online, lookup=lookup, auth=OnlineAuthSettings(sources=creds))
    return replace(cfg, online=online)


def test_metron_active_when_enabled_selected_and_credentialed() -> None:
    assert Runner(_metron_settings())._metron_is_active()


def test_metron_active_with_token_only() -> None:
    """A token-authenticated run still gets the burst-limit thread-pool cap."""
    settings = _metron_settings(user=None, password=None, key="t")
    assert Runner(settings)._metron_is_active()


def test_metron_inactive_when_lookup_disabled() -> None:
    assert not Runner(_metron_settings(enabled=False))._metron_is_active()


def test_metron_inactive_when_not_selected() -> None:
    assert not Runner(_metron_settings(sources=("comicvine",)))._metron_is_active()


def test_metron_inactive_without_credentials() -> None:
    assert not Runner(_metron_settings(user=None, password=None))._metron_is_active()


def test_metron_active_with_empty_sources_sentinel() -> None:
    """
    `sources=()` (the public ALL_SOURCES sentinel) means "every source".

    Unreachable via the CLI (config building collapses `()` to None) but
    reachable with a prebuilt settings object; the heuristic must apply
    falsy-collapse like `_build_active_online_sources` does, so the jobs
    cap still engages.
    """
    assert Runner(_metron_settings(sources=()))._metron_is_active()


def _capture_max_workers(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    """Record the `max_workers` each ThreadPoolExecutor is built with."""
    captured: list[int | None] = []

    class _Recorder(ThreadPoolExecutor):
        def __init__(self, max_workers: int | None = None, **kwargs) -> None:
            captured.append(max_workers)
            super().__init__(max_workers=max_workers, **kwargs)

    monkeypatch.setattr("comicbox.run.ThreadPoolExecutor", _Recorder)
    return captured


def test_run_parallel_caps_jobs_at_metron_burst_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """-j above the burst limit is clamped, and the clamp is explained."""
    captured = _capture_max_workers(monkeypatch)
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="INFO", format="{message}")
    try:
        Runner(_metron_settings())._run_parallel([], 32)
    finally:
        loguru_logger.remove(handler_id)
    assert captured == [METRON_DEFAULT_PER_MINUTE]
    assert any("Capping --jobs 32" in message for message in messages)


def test_run_parallel_keeps_jobs_when_metron_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_max_workers(monkeypatch)
    Runner(_metron_settings(enabled=False))._run_parallel([], 32)
    assert captured == [32]


def test_run_parallel_keeps_jobs_at_or_below_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_max_workers(monkeypatch)
    Runner(_metron_settings())._run_parallel([], 4)
    assert captured == [4]


# --------------------------------------------- real work through the pool


def _real_batch(tmp_path: Path) -> tuple[list[Path], Path]:
    """
    Three readable comics and one corrupt file, in a fixed sort order.

    `get_config` sorts `paths`, so the names are chosen to put the
    corrupt file second: the serial path then has exactly one successful
    file behind it, which is what makes the two error semantics below
    distinguishable.
    """
    source = Path(CIX_CBZ_SOURCE_PATH)
    good = []
    for name in ("a_good.cbz", "c_good.cbz", "d_good.cbz"):
        dest = tmp_path / name
        shutil.copy(source, dest)
        good.append(dest)
    corrupt = tmp_path / "b_corrupt.cbz"
    corrupt.write_bytes(b"this is not a zip archive")
    return good, corrupt


def _runner_for(paths: list[Path], jobs: int) -> Runner:
    return Runner(
        Namespace(
            comicbox=Namespace(
                paths=[str(p) for p in paths],
                general=Namespace(jobs=jobs),
            )
        )
    )


@contextmanager
def _captured_records() -> Generator[list[Any]]:
    """
    Collect loguru records. Must be entered *after* `Runner(...)`.

    `Runner.__init__` calls `init_logging`, which removes existing
    handlers — a handler added earlier would be gone before `run()`.
    """
    records: list[Any] = []
    handler_id = loguru_logger.add(lambda m: records.append(m.record), level="TRACE")
    try:
        yield records
    finally:
        loguru_logger.remove(handler_id)


def _messages(records: list[Any], text: str) -> list[Any]:
    return [r for r in records if text in r["message"]]


def _errors(records: list[Any]) -> list[Any]:
    return [r for r in records if r["level"].name == "ERROR"]


def test_parallel_batch_survives_a_corrupt_file(tmp_path: Path) -> None:
    """
    Unpatched `_run_one` over real archives: one bad file can't stop the pool.

    With no action flags set, each successfully opened comic logs
    "No action performed" exactly once, which is the per-file receipt
    this asserts on.
    """
    good, corrupt = _real_batch(tmp_path)
    runner = _runner_for([*good, corrupt], jobs=2)
    with _captured_records() as records:
        runner.run()  # completes; no exception escapes the pool

    assert len(_messages(records, "No action performed")) == len(good)
    errors = _errors(records)
    assert len(errors) == 1
    assert errors[0]["message"] == str(corrupt)
    assert isinstance(errors[0]["exception"].value, UnsupportedArchiveTypeError)


def test_parallel_batch_logs_each_failure_once(tmp_path: Path) -> None:
    """
    `_run_one` logs, then returns normally, so `future.result()` re-raises nothing.

    Both the worker's `except` and `_run_parallel`'s own `except` can log
    the same path; only one of them does.
    """
    good, corrupt = _real_batch(tmp_path)
    second_corrupt = tmp_path / "e_corrupt.cbz"
    second_corrupt.write_bytes(b"also not a zip")
    runner = _runner_for([*good, corrupt, second_corrupt], jobs=3)
    with _captured_records() as records:
        runner.run()

    errors = _errors(records)
    assert sorted(r["message"] for r in errors) == sorted(
        [str(corrupt), str(second_corrupt)]
    )
    assert len(_messages(records, "No action performed")) == len(good)


def test_serial_batch_aborts_on_a_corrupt_file(tmp_path: Path) -> None:
    """
    Documents a real asymmetry between the two dispatch paths.

    `_run_inner`'s serial branch calls `run_on_file` directly, and
    neither has an `except Exception` guard, so the first unreadable file
    ends the batch with a traceback. The parallel branch routes through
    `_run_one` — whose docstring is explicitly "swallowing exceptions for
    batch resilience" — and logs-and-continues instead.

    The guard arrived with `_run_one` in the parallel dispatch (v4.0.0);
    the pre-existing serial loop never had one, and only `recurse()` did.
    So this looks like an oversight rather than a decision: the same
    corrupt file is a logged error under `-j 2` and a fatal traceback
    under `-j 1`.
    """
    good, corrupt = _real_batch(tmp_path)
    runner = _runner_for([*good, corrupt], jobs=1)
    with _captured_records() as records, pytest.raises(UnsupportedArchiveTypeError):
        runner.run()

    # Only the file sorting before the corrupt one was processed; the two
    # after it never ran.
    assert len(_messages(records, "No action performed")) == 1
    assert _errors(records) == []


def test_recurse_batch_survives_a_corrupt_file(tmp_path: Path) -> None:
    """`recurse()` has the guard the serial explicit-path loop lacks."""
    good, corrupt = _real_batch(tmp_path)
    runner = Runner(
        Namespace(
            comicbox=Namespace(
                paths=[str(tmp_path)],
                general=Namespace(jobs=1, recurse=True),
            )
        )
    )
    with _captured_records() as records:
        runner.run()

    assert len(_messages(records, "No action performed")) == len(good)
    errors = _errors(records)
    assert len(errors) == 1
    assert errors[0]["message"] == str(corrupt)
