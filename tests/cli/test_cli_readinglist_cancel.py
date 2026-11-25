"""
Ctrl-C during ``comicbox rl match`` and ``comicbox rl write-arcs``.

Every comic is generated under tmp_path, or copied there from
tests/files: write-arcs changes comics, so no test points it at anything
else. Every write goes through the real ``bulk_write``.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from tests.util.comics import make_comic
from tests.util.readinglist_cli import (
    flat,
    read_tags,
    rl_write,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


# ------------------------------------------------------------------ match

# Loaded by the command and each of its workers: every read says it has
# begun, then is slowed down, so the Ctrl-C lands while comics are read.
_SLOW_READS = """
import time
from pathlib import Path

import comicbox.readinglists.library as library

_read = library._read_comic


def _slow(path, config):
    Path({marker!r}).touch()
    time.sleep(0.2)
    return _read(path, config)


library._read_comic = _slow
"""
_COMMAND = """
import sys

from comicbox.cli import main

if __name__ == "__main__":
    main(["comicbox", *sys.argv[1:]])
"""


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="needs process groups")
def test_ctrl_c_while_reading_is_one_line(
    reading_list: Path, library: Path, tmp_path: Path
) -> None:
    """
    A terminal's Ctrl-C goes to the reader's workers too.

    Each used to print its own KeyboardInterrupt traceback. Sent to the
    whole process group, as a terminal sends it, and twice, as ``uv run``
    passes it on: the second press cut the pool's shutdown short.
    """
    for number in range(40):
        make_comic(
            library / f"sonnet{number:02}.cbz",
            series="Sonnet",
            number=str(number),
            start_year=2012,
        )
    site = tmp_path / "site"
    site.mkdir()
    marker = tmp_path / "reading"
    (site / "sitecustomize.py").write_text(_SLOW_READS.format(marker=str(marker)))
    command = site / "command.py"
    command.write_text(_COMMAND)
    paths = [str(site), os.environ.get("PYTHONPATH", "")]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, paths))}
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(command), "rl", "match", str(reading_list), str(library)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        for _ in range(2):
            os.killpg(process.pid, signal.SIGINT)
            time.sleep(0.05)
        _, err = process.communicate(timeout=30)
    finally:
        # The whole group: a stuck reader's workers hold its pipes open.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()

    assert process.returncode == 130
    assert err.strip().splitlines() == ["Cancelled."]


# ------------------------------------------------------------- write-arcs


def _twenty_issues(tmp_path: Path) -> tuple[Path, Path]:
    """List Crimson Tide #1 to #20 and make a comic of each; return both."""
    numbers = [str(number) for number in range(1, 21)]
    listed = tmp_path / "list.yaml"
    listed.write_text(
        "reading_list:\n  name: Crimson Tide\n  entries:\n"
        + "".join(
            f"    - series: {{name: Crimson Tide, start_year: 2006}}\n"
            f"      issue: {{name: '{number}'}}\n"
            for number in numbers
        )
    )
    comics = tmp_path / "comics"
    for number in numbers:
        make_comic(
            comics / f"cw{number:>02}.cbz",
            series="Crimson Tide",
            number=number,
            start_year=2006,
        )
    return listed, comics


def _press_ctrl_c_in_the_first_write(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Have the first write press Ctrl-C three times; it adds its path to the list."""
    import comicbox.write

    original = comicbox.write.write_metadata
    pressed: list[Path] = []

    def interrupted(path: Path, *args: Any, **kwargs: Any) -> Any:
        if not pressed:
            pressed.append(path)
            for _ in range(3):
                os.kill(os.getpid(), signal.SIGINT)
                time.sleep(0.1)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(comicbox.write, "write_metadata", interrupted)
    return pressed


def test_ctrl_c_never_cuts_a_write_short(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Ctrl-C, however often pressed, lets the writes under way finish.

    The presses come from inside the first write, on the real bulk_write:
    no new write starts, and the process does not exit until they are done.
    """
    listed, comics = _twenty_issues(tmp_path)
    pressed = _press_ctrl_c_in_the_first_write(monkeypatch)

    code, out, err = rl_write(capsys, str(listed), str(comics), apply=True)

    said = flat(out)
    assert code == 130
    assert f"{pressed[0]} added 'Crimson Tide'" in said
    assert "not written: cancelled" in said
    assert "Stopping after the writes under way." in err
    assert err.endswith("Cancelled.")
    for path in comics.iterdir():
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
        written = f"{path} added" in said
        assert ("Crimson Tide" in (read_tags(path).get("arcs") or {})) is written
