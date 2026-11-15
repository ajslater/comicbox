"""
``comicbox readinglist`` and ``comicbox rl`` through the real CLI entry point.

Like the doctor, a special first argument that `cli.main` sniffs before
building a normal run; unlike it, a parser of its own with subcommands.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from comicbox.readinglists import cli as readinglist_cli
from comicbox.readinglists import load
from tests.const import CIX_CBZ_SOURCE_PATH, TEST_FILES_DIR

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator
    from pathlib import Path

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
CIVIL_WAR = READING_LISTS_DIR / "civil-war.yaml"
COMMON_CBL = READING_LISTS_DIR / "cbl" / "common.cbl"
TWO_DATABASES_CBL = READING_LISTS_DIR / "cbl" / "two-databases.cbl"
SMART_LIST = READING_LISTS_DIR / "cbl" / "smart-list.cbl"
FULL_JSON_CBL = READING_LISTS_DIR / "json-cbl" / "full.json"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Point loguru back at stdout; the command bound it to the captured one."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """Run the CLI; return its exit code and its stdout and stderr, unwrapped."""
    code = 0
    try:
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, " ".join(captured.out.split()), " ".join(captured.err.split())


@pytest.mark.parametrize("command", ["readinglist", "rl"])
def test_print(capsys: pytest.CaptureFixture[str], command: str) -> None:
    code, out, _ = _run(capsys, command, "print", str(CIVIL_WAR), str(COMMON_CBL))
    assert code == 0
    assert "Civil War" in out
    assert "[Marvel] Civil War (Hand Written)" in out
    assert "comicvine:105747" in out


def test_print_reports_a_bad_file_and_carries_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "rl", "print", str(SMART_LIST), str(COMMON_CBL))
    assert code == 1
    assert "smart list" in err
    assert "[Marvel] Civil War (Hand Written)" in out


def test_validate(capsys: pytest.CaptureFixture[str]) -> None:
    paths = (CIVIL_WAR, FULL_JSON_CBL, COMMON_CBL)
    code, out, _ = _run(capsys, "rl", "validate", *map(str, paths))
    assert code == 0
    assert out.count("✓") == 3
    assert "json-cbl, 4 entries" in out


def test_validate_fails_on_any_bad_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    document = json.loads(FULL_JSON_CBL.read_text())
    del document["issueList"][0]["seriesStartYear"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(document))
    junk = tmp_path / "junk.txt"
    junk.write_text("junk")
    code, out, _ = _run(
        capsys, "rl", "validate", str(COMMON_CBL), str(bad), str(junk), str(SMART_LIST)
    )
    assert code == 1
    assert out.count("✓") == 1
    assert out.count("✗") == 3
    assert "'seriesStartYear' is a required property" in out
    assert "not a reading list" in out


def test_convert(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = _run(
        capsys,
        "rl",
        "convert",
        "--to",
        "json-cbl",
        "-o",
        str(tmp_path),
        str(COMMON_CBL),
    )
    assert code == 0
    assert "lost: entries[0, 1, 2].date.cover_date" in err
    result = load(tmp_path / "common.json")
    assert result.fmt.name == "JSON_CBL"
    assert len(result.reading_list["entries"]) == 3


def test_convert_never_overwrites_its_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "list.json"
    shutil.copy(FULL_JSON_CBL, source)
    before = source.read_text()
    code, _, err = _run(capsys, "rl", "convert", "--to", "json", str(source))
    assert code == 1
    assert "overwrite the input" in err
    assert source.read_text() == before


def test_combine(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(
        capsys, "rl", "combine", str(TWO_DATABASES_CBL), str(COMMON_CBL)
    )
    assert code == 0
    assert out.startswith("reading_list: name: Civil War")
    assert f"{TWO_DATABASES_CBL}: 2 entries added" in err
    assert f"{COMMON_CBL}: 1 entry added" in err


def test_combine_to_a_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    output = tmp_path / "combined.cbl"
    code, out, _ = _run(
        capsys,
        "rl",
        "combine",
        "--to",
        "cbl",
        "-o",
        str(output),
        str(TWO_DATABASES_CBL),
        str(COMMON_CBL),
    )
    assert code == 0
    assert not out
    assert len(load(output).reading_list["entries"]) == 3


def test_combine_stops_on_a_bad_input(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "rl", "combine", str(COMMON_CBL), str(SMART_LIST))
    assert code == 1
    assert not out


def test_compare(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(
        capsys, "rl", "compare", str(COMMON_CBL), str(TWO_DATABASES_CBL)
    )
    assert code == 0
    assert "Verdict subset" in out
    assert "B in A 1.00" in out


def test_from_arcs(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    comics = tmp_path / "comics"
    comics.mkdir()
    shutil.copy(CIX_CBZ_SOURCE_PATH, comics / "a.cbz")
    output = tmp_path / "lists"
    code, _, err = _run(capsys, "rl", "from-arcs", "-o", str(output), str(comics))
    assert code == 0
    written = sorted(path.name for path in output.iterdir())
    assert written
    assert all(name.endswith(".yaml") for name in written)
    assert "written as" in err
    reading_list = load(output / written[0]).reading_list
    assert reading_list["sources"][0] == {"kind": "tags"}


def test_from_arcs_needs_a_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = _run(capsys, "rl", "from-arcs", str(tmp_path / "gone"))
    assert code == 1
    assert "not a directory" in err


@pytest.mark.parametrize(
    "argv",
    [
        ("rl",),
        ("rl", "bogus"),
        ("rl", "compare", "a"),
        ("rl", "convert", "--to", "x", "a"),
    ],
    ids=["no-action", "unknown-action", "missing-file", "unknown-format"],
)
def test_usage_errors_exit_two(
    capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    assert _run(capsys, *argv)[0] == 2


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "readinglist", "--help")
    assert code == 0
    assert out.startswith("usage: comicbox readinglist")
    assert "from-arcs" in out


@pytest.mark.parametrize("name", ["./readinglist", "./rl"])
def test_dot_slash_is_a_path(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """A comic file named readinglist or rl is reachable, as ./readinglist."""
    seen = []

    class FakeRunner:
        failure_count = 0

        def __init__(self, args: Namespace) -> None:
            seen.append(args.comicbox.paths)

        def run(self) -> None:
            pass

    def no_readinglist(*_args: object) -> int:
        reason = "dispatched to readinglist"
        raise AssertionError(reason)

    monkeypatch.setattr(cli, "Runner", FakeRunner)
    monkeypatch.setattr(readinglist_cli, "main", no_readinglist)
    cli.main(("comicbox", name))
    assert seen == [[name]]


def test_main_help_names_reading_lists(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "--help")
    assert code == 0
    assert "comicbox rl ACTION" in out
    assert "./readinglist" in out


def test_compare_an_unordered_list(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    unordered = tmp_path / "tags.yaml"
    text = CIVIL_WAR.read_text().replace("ordered: true", "ordered: false")
    unordered.write_text(text)
    code, out, _ = _run(capsys, "rl", "compare", str(CIVIL_WAR), str(unordered))
    assert code == 0
    assert "Verdict same" in out
    assert "Order agreement n/a" in out
