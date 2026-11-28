"""
`--validate` fails an invalid comic and goes on to the next.

It called `sys.exit(1)` from inside the box, which the Runner's per-file
guard cannot catch, so the first invalid comic ended the run and every
comic after it went unvalidated, unexported and unwritten.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from loguru import logger as loguru_logger

from comicbox import cli, logger
from tests.util.comics import make_comic

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_BOGUS_CIX = "<ComicInfo><Bogus>x</Bogus></ComicInfo>"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """`cli.main` binds loguru to the swapped stdout; rebind it after."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run_cli(*argv: str) -> tuple[int, str]:
    """Run the CLI, its log bound to the returned stdout whatever ran before."""
    logger._initialized_key = None
    old_stdout = sys.stdout
    buf = StringIO()
    code = 0
    try:
        sys.stdout = buf
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    finally:
        # The sink is enqueued: drain it before the buffer is read.
        loguru_logger.complete()
        sys.stdout = old_stdout
    return code, buf.getvalue()


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_an_invalid_comic_does_not_end_the_batch(tmp_path: Path, jobs: str) -> None:
    bad = make_comic(
        tmp_path / "a_bad.cbz", files={"ComicInfo.xml": _BOGUS_CIX}, series="Bad", number="1"
    )
    good = make_comic(tmp_path / "b_good.cbz", series="Good", number="1")
    code, out = _run_cli("-j", jobs, "--validate", str(bad), str(good))
    assert code == 1
    assert "1 file(s) failed." in out
    assert out.count("Metadata validation succeeded") == 1
    assert "ComicInfo: failed validation" in out
    assert "Traceback" not in out


def test_a_valid_comic_exits_zero(tmp_path: Path) -> None:
    good = make_comic(tmp_path / "good.cbz", series="Good", number="1")
    code, out = _run_cli("--validate", str(good))
    assert code == 0
    assert "Metadata validation succeeded" in out
