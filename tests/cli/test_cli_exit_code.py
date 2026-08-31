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
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from tests.const import CIX_CBZ_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
