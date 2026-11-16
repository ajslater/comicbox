"""
Running ``comicbox rl`` in-process, and reading back what it wrote.

Shared by the ``tests/cli/test_cli_readinglist*`` modules. Their fixtures,
and the one that restores logging and Ctrl-C after each test, are in
``tests/cli/conftest.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.readinglists.library import read_comics
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

CIX = "COMIC_INFO"
MI = "METRON_INFO"

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
CIVIL_WAR = READING_LISTS_DIR / "civil-war.yaml"
COMMON_CBL = READING_LISTS_DIR / "cbl" / "common.cbl"
TWO_DATABASES_CBL = READING_LISTS_DIR / "cbl" / "two-databases.cbl"
SMART_LIST = READING_LISTS_DIR / "cbl" / "smart-list.cbl"
FULL_JSON_CBL = READING_LISTS_DIR / "json-cbl" / "full.json"

CIVIL_WAR_LIST = """reading_list:
  name: Civil War
  entries:
    - series: {name: Civil War, start_year: 2006}
      issue: {name: '1'}
    - series: {name: Civil War, start_year: 2006}
      issue: {name: '2'}
    - series: {name: Amazing Spider-Man, start_year: 1963}
      issue: {name: '532'}
    - series: {name: Civil War, start_year: 2006}
      issue: {name: '7'}
"""


def write_list(path: Path, name: str = "Civil War", body: str = CIVIL_WAR_LIST) -> Path:
    """Write a reading list, named *name*, to *path*."""
    path.write_text(
        body.replace("name: Civil War\n  entries", f"name: {name}\n  entries")
    )
    return path


def exit_code(*argv: str) -> int:
    """Run ``comicbox *argv``; return its exit code."""
    try:
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def rl_main(*argv: str) -> int:
    """Run ``comicbox rl *argv``; return its exit code."""
    return exit_code("rl", *argv)


def flat(text: str) -> str:
    """Join *text*'s words with single spaces, undoing any wrapping."""
    return " ".join(text.split())


def cli_run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """Run ``comicbox *argv``; return its exit code and its stdout and stderr, flat."""
    code = exit_code(*argv)
    captured = capsys.readouterr()
    return code, flat(captured.out), flat(captured.err)


def rl_run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """Run ``comicbox rl *argv``; return its exit code, its stdout, and its stderr flat."""
    code = rl_main(*argv)
    captured = capsys.readouterr()
    return code, captured.out, flat(captured.err)


def rl_write(
    capsys: pytest.CaptureFixture[str], *argv: str, apply: bool = False
) -> tuple[int, str, str]:
    """Run write-arcs, with -w json unless the test gives its own -w."""
    options = ["--apply"] if apply else []
    if "-w" not in argv:
        options += ["-w", "json"]
    return rl_run(capsys, "write-arcs", *options, *argv)


def read_arcs(directory: Path) -> dict[str, Any]:
    """Map each comic under *directory*, by file name, to its arcs."""
    return {
        path.name: comic.tags.get("arcs")
        for path, comic in read_comics(directory).comics.items()
    }


def read_tags(path: Path) -> dict[str, Any]:
    """Read a comic's comicbox tags."""
    with Comicbox(path) as box:
        return dict(box.to_dict()["comicbox"])
