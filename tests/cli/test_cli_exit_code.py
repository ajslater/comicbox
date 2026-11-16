"""
CLI exit-code tests for partially-failed batches.

Batch dispatch logs a failed file and keeps going, so the exit code is
the only thing a script can check. Before the guard was unified, a
serial run reported failure by letting the first bad file escape — which
also abandoned every file behind it — and a `-j 2` run over the same
batch exited 0.

That the surviving files are still processed is asserted precisely, off
the log records, in `tests/unit/test_run_parallel.py`.
"""

from __future__ import annotations

import shutil
import sys
from io import StringIO
from typing import TYPE_CHECKING, Any

import pytest

from comicbox import cli, logger
from tests.const import CBI_CBR_SOURCE_PATH, CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """
    Point loguru back at the real stdout when the test is done.

    `cli.main` builds a `Runner`, which calls `init_logging` and binds a
    loguru sink to whatever `sys.stdout` is at that moment — here, the
    buffer below. `init_logging` then memoizes, so without this every
    later test in the session logs into that dead buffer.
    """
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _batch(tmp_path: Path) -> tuple[list[Path], Path]:
    good = []
    for name in ("a_good.cbz", "c_good.cbz"):
        dest = tmp_path / name
        shutil.copy(CIX_CBZ_SOURCE_PATH, dest)
        good.append(dest)
    corrupt = tmp_path / "b_corrupt.cbz"
    corrupt.write_bytes(b"not a zip")
    return good, corrupt


def _run_cli(*argv: str) -> tuple[int, str]:
    """Run `cli.main`, returning its exit code (0 when it didn't exit) and stdout."""
    old_stdout = sys.stdout
    buf = StringIO()
    code = 0
    try:
        sys.stdout = buf
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        sys.stdout = old_stdout
    return code, buf.getvalue()


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_partial_failure_exits_one(tmp_path: Path, jobs: str) -> None:
    """Same batch, same exit code, whatever `-j` says."""
    good, corrupt = _batch(tmp_path)
    code, out = _run_cli("-j", jobs, *(str(p) for p in [*good, corrupt]))
    assert code == 1
    assert "1 file(s) failed." in out


def test_clean_batch_exits_zero(tmp_path: Path) -> None:
    good, _corrupt = _batch(tmp_path)
    code, out = _run_cli(*(str(p) for p in good))
    assert code == 0
    assert "failed" not in out


def test_single_corrupt_file_exits_one(tmp_path: Path) -> None:
    """The common interactive case keeps its non-zero exit."""
    _good, corrupt = _batch(tmp_path)
    code, out = _run_cli(str(corrupt))
    assert code == 1
    assert "1 file(s) failed." in out


def test_every_file_failing_exits_one(tmp_path: Path) -> None:
    """A `-j N` batch where nothing succeeded used to exit 0."""
    corrupt = []
    for name in ("a.cbz", "b.cbz", "c.cbz"):
        path = tmp_path / name
        path.write_bytes(b"not a zip")
        corrupt.append(path)
    code, out = _run_cli("-j", "2", *(str(p) for p in corrupt))
    assert code == 1
    assert "3 file(s) failed." in out


def _one_line(out: str) -> str:
    """Undo rich's wrapping of a long message at the terminal width."""
    return " ".join(out.split())


def test_bad_config_value_exits_one_without_traceback(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("comicbox:\n  general:\n    jobs: lots\n")
    code, out = _run_cli("-c", str(config), "-v")
    assert code == 1
    assert "comicbox.general.jobs: must be a number" in _one_line(out)


def test_bad_config_enum_exits_one_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__MATCH", "bogus")
    code, out = _run_cli("-v")
    assert code == 1
    assert "--match: unknown name 'bogus'" in _one_line(out)


def test_config_error_brackets_survive_rich(tmp_path: Path) -> None:
    """Paths like "[digital]" are text, not rich markup to swallow."""
    missing = tmp_path / "Foo [digital].yaml"
    code, out = _run_cli("-c", str(missing), "-v")
    assert code == 1
    assert "Foo [digital].yaml could not be read" in _one_line(out)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])


def _logged(monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str, str]:
    """Run ``cli.main``; return its exit code, stdout, and what it logged, tracebacks too."""
    from loguru import logger as loguru_logger

    # The runner replaces every sink with its own, enqueued; keep this one.
    monkeypatch.setattr("comicbox.run.init_logging", lambda *_: None)
    messages: list[str] = []
    handler = loguru_logger.add(messages.append, format="{message}\n{exception}")
    try:
        code, out = _run_cli(*argv)
    finally:
        loguru_logger.remove(handler)
    return code, out, "".join(messages)


def _occupied(tmp_path: Path) -> tuple[tuple[str, ...], str]:
    comic = tmp_path / "c.cbr"
    shutil.copy(CBI_CBR_SOURCE_PATH, comic)
    comic.with_suffix(".cbz").write_text("someone else's comic")
    return ("--cbz", str(comic)), "c.cbz already exists"


def _not_a_directory(tmp_path: Path) -> tuple[tuple[str, ...], str]:
    comic = tmp_path / "x.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, comic)
    target = tmp_path / "notadir"
    target.touch()
    return ("-x", "0", "-d", str(target), str(comic)), "is not a directory"


@pytest.mark.parametrize("refusal", [_occupied, _not_a_directory])
def test_a_deliberate_refusal_is_one_line_and_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: Any
) -> None:
    """B1: an occupied destination, the 5.2.0 refusal, printed a traceback."""
    argv, message = refusal(tmp_path)

    code, out, logged = _logged(monkeypatch, *argv)

    assert code == 1
    assert "1 file(s) failed." in out
    assert message in logged
    assert "Traceback" not in logged


def test_an_unexpected_failure_keeps_its_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from comicbox.run import Runner

    def boom(*_: Any) -> None:
        reason = "boom"
        raise RuntimeError(reason)

    monkeypatch.setattr(Runner, "run_on_file", boom)
    comic = tmp_path / "x.cbz"
    shutil.copy(CIX_CBZ_SOURCE_PATH, comic)

    code, _, logged = _logged(monkeypatch, "-p", str(comic))

    assert code == 1
    assert "Traceback" in logged
    assert "RuntimeError: boom" in logged


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_a_missing_path_fails_once_and_the_rest_still_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jobs: str
) -> None:
    """A path naming nothing was logged twice and the run exited 0."""
    good, _corrupt = _batch(tmp_path)
    missing = tmp_path / "no_such.cbz"

    code, out, logged = _logged(
        monkeypatch, "-j", jobs, str(missing), *(str(p) for p in good)
    )

    assert code == 1
    assert "1 file(s) failed." in out
    assert logged.count(f"{missing} does not exist.") == 1
    assert "Traceback" not in logged
    assert logged.count("No action performed") == len(good)


def test_a_lone_missing_path_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, logged = _logged(monkeypatch, "-j", "2", str(tmp_path / "no.cbz"))
    assert code == 1
    assert "1 file(s) failed." in out
    assert "No files to process" not in logged
