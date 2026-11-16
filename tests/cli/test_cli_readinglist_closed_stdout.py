"""
A reader closing ``comicbox rl``'s stdout is not an error (B17).

Rich exits 1 on a broken pipe, so ``rl print FILE | head -1`` failed, and a
``write-arcs --apply`` piped into ``head`` stopped tagging part way. Every
action that runs offline is run here with a stdout whose reader has gone.
"""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from comicbox import cli, logger
from comicbox.readinglists.library import read_comics
from tests.util.comics import make_comic

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_LIST = """reading_list:
  name: Civil War
  entries:
    - series: {name: Civil War, start_year: 2006}
      issue: {name: '1'}
    - series: {name: Civil War, start_year: 2006}
      issue: {name: '2'}
"""


# The console script's entry point; argv[0] is "-c", and main skips it.
_ENTRY = "from comicbox.cli import main; main()"


class _ClosedPipe(io.StringIO):
    """A stdout whose reader has gone, as ``| head -1`` leaves it."""

    @override
    def write(self, s: str) -> int:
        """Fail as a write to a closed pipe does."""
        del s
        raise BrokenPipeError(32, "Broken pipe")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    handler = signal.getsignal(signal.SIGINT)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, handler)
        logger._initialized_key = None
        logger.init_logging()


@pytest.fixture
def reading_list(tmp_path: Path) -> Path:
    path = tmp_path / "civil-war.yaml"
    path.write_text(_LIST)
    return path


@pytest.fixture
def library(tmp_path: Path) -> Path:
    directory = tmp_path / "comics"
    for number in ("1", "2"):
        make_comic(
            directory / f"cw{number}.cbz",
            series="Civil War",
            number=number,
            start_year=2006,
        )
    return directory


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "stdout", _ClosedPipe())
    try:
        cli.main(("comicbox", "rl", *argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        monkeypatch.undo()
    return 0


def _arcs(directory: Path) -> dict[str, Any]:
    return {
        path.name: comic.tags.get("arcs")
        for path, comic in read_comics(directory).comics.items()
    }


@pytest.mark.parametrize(
    "argv",
    [
        ("print", "{list}"),
        ("validate", "{list}"),
        ("convert", "{list}", "--to", "json"),
        ("combine", "{list}", "{list}"),
        ("compare", "{list}", "{list}"),
        ("match", "{list}", "{comics}"),
        ("write-arcs", "{list}", "{comics}", "-w", "json"),
        ("from-arcs", "{comics}", "-o", "{out}"),
    ],
    ids=lambda argv: argv[0],
)
def test_every_action_exits_quietly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    reading_list: Path,
    library: Path,
    argv: tuple[str, ...],
) -> None:
    names = {"list": reading_list, "comics": library, "out": tmp_path / "out"}
    code = _main(monkeypatch, *(arg.format(**names) for arg in argv))

    assert code == 0
    assert "Broken pipe" not in capsys.readouterr().err


def test_write_arcs_apply_finishes_its_writes(
    monkeypatch: pytest.MonkeyPatch, reading_list: Path, library: Path
) -> None:
    """It reports each write on stdout, and stopped at the first."""
    code = _main(
        monkeypatch,
        "write-arcs",
        "--apply",
        "-w",
        "json",
        str(reading_list),
        str(library),
    )

    assert code == 0
    assert _arcs(library) == {
        "cw1.cbz": {"Civil War": {"number": 1}},
        "cw2.cbz": {"Civil War": {"number": 2}},
    }


def test_a_closed_pipe_exits_0_with_nothing_on_stderr(reading_list: Path) -> None:
    """The real thing: a pipe closed before comicbox writes to it."""
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _ENTRY, "rl", "print", str(reading_list)],
            stdout=write_end,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        os.close(write_end)

    assert done.returncode == 0
    assert done.stderr == b""
