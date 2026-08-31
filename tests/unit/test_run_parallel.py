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

from loguru import logger as loguru_logger
from typing_extensions import Self

from comicbox.config import get_config
from comicbox.config.online.settings import OnlineAuthSettings, OnlineSourceCredentials
from comicbox.formats.base.online.rate_limits import METRON_DEFAULT_PER_MINUTE
from comicbox.formats.base.online.series_cache import SeriesCache
from comicbox.run import Runner
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest

    from comicbox.config.settings import ComicboxSettings


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
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    assert str(corrupt) in errors[0]["message"]
    assert runner.failure_count == 1


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
    assert len(errors) == 2
    assert {str(corrupt), str(second_corrupt)} == {
        r["message"].rsplit(": ", 1)[-1] for r in errors
    }
    assert len(_messages(records, "No action performed")) == len(good)
    assert runner.failure_count == 2


def test_serial_batch_survives_a_corrupt_file(tmp_path: Path) -> None:
    """
    `-j 1` is as resilient as `-j 2` — the asymmetry this used to pin.

    The serial branch called `run_on_file` directly and neither had a
    guard, so the first unreadable file ended the batch and every file
    sorting after it went unprocessed. Both branches now route through
    `_run_one`.
    """
    good, corrupt = _real_batch(tmp_path)
    runner = _runner_for([*good, corrupt], jobs=1)
    with _captured_records() as records:
        runner.run()

    assert len(_messages(records, "No action performed")) == len(good)
    assert len(_errors(records)) == 1
    assert runner.failure_count == 1


def test_serial_and_parallel_agree_on_a_corrupt_file(tmp_path: Path) -> None:
    """The same batch, the same outcome, whatever `-j` says."""

    def outcome(jobs: int, root: Path) -> tuple[int, int]:
        good, _corrupt = _real_batch(root)
        runner = _runner_for([*good, root / "b_corrupt.cbz"], jobs=jobs)
        with _captured_records() as records:
            runner.run()
        return len(_messages(records, "No action performed")), runner.failure_count

    serial = outcome(1, tmp_path / "serial")
    parallel = outcome(2, tmp_path / "parallel")
    assert serial == parallel == (3, 1)


def test_expected_archive_errors_log_without_a_traceback(tmp_path: Path) -> None:
    """
    "Not a comic" is a message, not a bug — it doesn't earn a stack.

    Unexpected failures still get `logger.exception`; this is the one
    class of per-file error the user can act on directly.
    """
    good, corrupt = _real_batch(tmp_path)
    runner = _runner_for([*good, corrupt], jobs=1)
    with _captured_records() as records:
        runner.run()

    error = _errors(records)[0]
    assert error["exception"] is None
    assert "Unsupported archive type" in error["message"]


def test_run_resets_the_failure_count(tmp_path: Path) -> None:
    """A reused Runner reports this run's failures, not the last one's."""
    good, corrupt = _real_batch(tmp_path)
    runner = _runner_for([*good, corrupt], jobs=1)
    with _captured_records():
        runner.run()
    assert runner.failure_count == 1

    runner._config = replace(runner._config, paths=tuple(str(p) for p in good))
    with _captured_records():
        runner.run()
    assert runner.failure_count == 0


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
    assert str(corrupt) in errors[0]["message"]
    assert runner.failure_count == 1


# ------------------------------------------------ CLI series batching


def _online_runner(tmp_path: Path, names: list[str]) -> tuple[Runner, list[str]]:
    """Build a Runner over `names` with online lookup enabled."""
    for name in names:
        (tmp_path / name).write_bytes(b"")
    settings = _metron_settings()
    paths = tuple(str(tmp_path / name) for name in names)
    return Runner(replace(settings, paths=paths)), list(paths)


def test_runner_owns_one_series_cache_for_the_batch() -> None:
    """
    The CLI gets a series cache; it used to have none at all.

    Without it, `comicbox --online` re-ran the full candidate search for
    every issue of a series even inside a single batch — the exact work
    `OnlineSession` has always skipped.
    """
    runner = Runner(_metron_settings())
    assert isinstance(runner._series_cache, SeriesCache)
    assert len(runner._series_cache) == 0


def test_series_cache_is_wired_into_each_box(tmp_path: Path) -> None:
    """Every file of an online batch shares the runner's one cache."""
    runner, paths = _online_runner(tmp_path, ["Spider-Man #001 (2018).cbz"])
    seen: list[Any] = []

    class _FakeBox:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def set_series_cache(self, cache: Any) -> None:
            seen.append(cache)

        def print_file_header(self) -> None:
            return None

        def run(self) -> None:
            return None

    with patch("comicbox.run.Comicbox", lambda *_a, **_kw: _FakeBox()):
        runner.run_on_file(paths[0])
    assert seen == [runner._series_cache]


def test_online_batch_is_clustered_by_series(tmp_path: Path) -> None:
    """
    Same-series files run back-to-back so the cache's cold path runs once.

    Interleaved input order is the realistic case — a recursive walk
    sorts by path, which mixes series whenever they share a directory.
    """
    names = [
        "Spider-Man #001 (2018).cbz",
        "Batman #001 (2011).cbz",
        "Spider-Man #014 (2019).cbz",
        "Batman #027 (2013).cbz",
    ]
    runner, paths = _online_runner(tmp_path, names)
    ordered = [
        Path(p).name for p in runner._order_for_series_batching(list(map(Path, paths)))
    ]
    spider = [i for i, n in enumerate(ordered) if n.startswith("Spider")]
    batman = [i for i, n in enumerate(ordered) if n.startswith("Batman")]
    assert spider == [spider[0], spider[0] + 1]
    assert batman == [batman[0], batman[0] + 1]


def test_offline_batch_keeps_user_order(tmp_path: Path) -> None:
    """Reordering is an online-lookup optimization; nothing else pays for it."""
    names = ["z.cbz", "a.cbz", "m.cbz"]
    for name in names:
        (tmp_path / name).write_bytes(b"")
    paths = [tmp_path / name for name in names]
    runner = Runner(get_config(Namespace(comicbox=Namespace())))
    assert runner._order_for_series_batching(paths) == paths
