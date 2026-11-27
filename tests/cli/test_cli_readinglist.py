"""
``comicbox readinglist`` and ``comicbox rl`` through the real CLI entry point.

Like the doctor, a special first argument that `cli.main` sniffs before
building a normal run; unlike it, a parser of its own with subcommands.
Where the actions write, and how they report bad input, is in
``test_cli_readinglist_files``.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox import cli
from comicbox.readinglists import ReadingListFormats, load
from comicbox.readinglists import cli as readinglist_cli
from tests.const import CIX_CBZ_SOURCE_PATH, METRON_CBZ_FN, TEST_FILES_DIR
from tests.util.readinglist_cli import (
    COMMON_CBL,
    CRIMSON_TIDE,
    FULL_JSON_CBL,
    SMART_LIST,
    TWO_DATABASES_CBL,
    cli_run,
)

if TYPE_CHECKING:
    from argparse import Namespace
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


@pytest.mark.parametrize("command", ["readinglist", "rl"])
def test_print(capsys: pytest.CaptureFixture[str], command: str) -> None:
    code, out, _ = cli_run(capsys, command, "print", str(CRIMSON_TIDE), str(COMMON_CBL))
    assert code == 0
    assert "Crimson Tide" in out
    assert "[Marvel] Crimson Tide (Hand Written)" in out
    assert "comicvine:105747" in out


def test_print_reports_a_bad_file_and_carries_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = cli_run(capsys, "rl", "print", str(SMART_LIST), str(COMMON_CBL))
    assert code == 1
    assert "smart list" in err
    assert "[Marvel] Crimson Tide (Hand Written)" in out


def test_print_carries_on_past_a_cbl_of_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A ``<ReadingList>`` holding only text stopped the batch with a traceback."""
    bad = tmp_path / "bad.cbl"
    bad.write_text('<?xml version="1.0"?><ReadingList>hello</ReadingList>')
    code, out, err = cli_run(capsys, "rl", "print", str(bad), str(COMMON_CBL))
    assert code == 1
    assert "bad.cbl" in err
    assert "[Marvel] Crimson Tide (Hand Written)" in out


def test_validate(capsys: pytest.CaptureFixture[str]) -> None:
    paths = (CRIMSON_TIDE, FULL_JSON_CBL, COMMON_CBL)
    code, out, _ = cli_run(capsys, "rl", "validate", *map(str, paths))
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
    code, out, _ = cli_run(
        capsys, "rl", "validate", str(COMMON_CBL), str(bad), str(junk), str(SMART_LIST)
    )
    assert code == 1
    assert out.count("✓") == 1
    assert out.count("✗") == 3
    assert "'seriesStartYear' is a required property" in out
    assert "Not a reading list in any format" in out


def test_convert_names_no_loss_for_what_the_format_adds(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "x.yaml"
    source.write_text(
        "reading_list:\n  name: X\n  entries:\n"
        "    - series: {name: Bladehawk, start_year: 2016}\n"
        "      issue: {name: '1'}\n      date: {year: 2016}\n"
    )
    code, _, err = cli_run(capsys, "rl", "convert", "--to", "cbl", str(source))
    assert code == 0
    assert "lost" not in err


def test_convert(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = cli_run(
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
    # A whole cover date is written for the year: the year is lost, and the
    # cover date added is not named.
    assert "lost: entries.date.year" in err
    assert "lost: entries.date.cover_date" not in err
    result = load(tmp_path / "common.json")
    assert result.fmt is ReadingListFormats.JSON_CBL
    assert len(result.reading_list["entries"]) == 3


def test_combine(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = cli_run(
        capsys, "rl", "combine", str(TWO_DATABASES_CBL), str(COMMON_CBL)
    )
    assert code == 0
    assert out.startswith("reading_list: name: Crimson Tide")
    assert f"{TWO_DATABASES_CBL}: 2 entries added" in err
    assert f"{COMMON_CBL}: 1 entry added" in err


def test_combine_to_a_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    output = tmp_path / "combined.cbl"
    code, out, _ = cli_run(
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
    code, out, _ = cli_run(capsys, "rl", "combine", str(COMMON_CBL), str(SMART_LIST))
    assert code == 1
    assert not out


def test_compare(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = cli_run(
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
    code, _, err = cli_run(capsys, "rl", "from-arcs", "-o", str(output), str(comics))
    assert code == 0
    written = sorted(path.name for path in output.iterdir())
    assert written
    assert all(name.endswith(".yaml") for name in written)
    assert "written as" in err
    reading_list = load(output / written[0]).reading_list
    assert reading_list["sources"][0] == {"kind": "tags"}


def test_from_arcs_reads_every_tag_format(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """``read.formats: [cix]`` in the user's config emptied it for MetronInfo arcs."""
    # COMICBOXDIR is tmp_path, so this is the user's config.
    (tmp_path / "config.yaml").write_text("comicbox:\n  read:\n    formats: [cix]\n")
    comics = tmp_path / "comics"
    comics.mkdir()
    shutil.copy(TEST_FILES_DIR / METRON_CBZ_FN, comics / "a.cbz")
    output = tmp_path / "lists"
    code, _, _ = cli_run(capsys, "rl", "from-arcs", "-o", str(output), str(comics))
    assert code == 0
    assert sorted(path.name for path in output.iterdir()) == [
        "Captain Arc.yaml",
        "Other Arc.yaml",
    ]


def test_from_arcs_needs_a_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = cli_run(capsys, "rl", "from-arcs", str(tmp_path / "gone"))
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
    assert cli_run(capsys, *argv)[0] == 2


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = cli_run(capsys, "readinglist", "--help")
    assert code == 0
    assert out.startswith("Usage: comicbox readinglist")
    assert "from-arcs" in out


def test_every_action_help_is_rich() -> None:
    """Each action's --help is rich, as comicbox's own is."""
    from argparse import _SubParsersAction

    from rich_argparse import RichHelpFormatter

    parser = readinglist_cli.build_parser()
    (actions,) = (
        action for action in parser._actions if isinstance(action, _SubParsersAction)
    )
    plain = [
        name
        for name, sub in actions.choices.items()
        if not issubclass(sub.formatter_class, RichHelpFormatter)
    ]
    assert not plain, f"rl actions with plain help: {plain}"


def test_main_help_names_every_action() -> None:
    """`comicbox -h` lists every reading-list action `comicbox rl` has."""
    from rich.text import Text

    from comicbox.cli.epilog import _READING_LIST_MODE

    text = Text.from_markup(str(_READING_LIST_MODE.renderable)).plain
    missing = [
        action
        for action in readinglist_cli._ACTIONS
        if not re.search(rf"(?<![\w-]){re.escape(action)}(?![\w-])", text)
    ]
    assert not missing, f"comicbox -h does not name rl actions: {missing}"


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
    code, out, _ = cli_run(capsys, "--help")
    assert code == 0
    assert "comicbox rl ACTION" in out
    assert "./readinglist" in out


def test_compare_an_unordered_list(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    unordered = tmp_path / "tags.yaml"
    text = CRIMSON_TIDE.read_text().replace("ordered: true", "ordered: false")
    unordered.write_text(text)
    code, out, _ = cli_run(capsys, "rl", "compare", str(CRIMSON_TIDE), str(unordered))
    assert code == 0
    assert "Verdict same" in out
    assert "Order agreement n/a" in out


def test_validate_prints_what_a_read_drops(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    typo = tmp_path / "typo.yaml"
    misspelled = "descripton"  # codespell:ignore
    typo.write_text(CRIMSON_TIDE.read_text().replace("description:", f"{misspelled}:"))
    code, out, _ = cli_run(capsys, "rl", "validate", str(typo))
    assert code == 0
    assert f"warning: {misspelled}: 'The superhuman registration act" in out


def test_the_title_is_not_wrapped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    name = "A Reading List With A Rather Long Name Of Fifty Chars"
    path = tmp_path / "long.yaml"
    path.write_text(f"reading_list:\n  name: {name}\n  notes: n\n")
    with contextlib.suppress(SystemExit):
        cli.main(("comicbox", "rl", "print", str(path)))
    assert name in capsys.readouterr().out.splitlines()
