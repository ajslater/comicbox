"""
``comicbox rl``: the files it writes, and how it reports what it reads.

An input, or a file already there, is never written over; stdout carries
only the list; and a bad file is one line on stderr.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox.readinglists import cli as readinglist_cli
from comicbox.readinglists import load, loads
from tests.const import CIX_CBZ_SOURCE_PATH
from tests.util.readinglist_cli import (
    COMMON_CBL,
    FULL_JSON_CBL,
    TWO_DATABASES_CBL,
    cli_run,
    exit_code,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


def test_convert_never_overwrites_its_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "list.json"
    shutil.copy(FULL_JSON_CBL, source)
    before = source.read_text()
    code, _, err = cli_run(capsys, "rl", "convert", "--to", "json", str(source))
    assert code == 1
    assert "is one of the inputs" in err
    assert source.read_text() == before


def test_convert_writes_nothing_when_a_destination_is_an_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """a.cbl would become a.json, which is the other input."""
    cbl, json_cbl = tmp_path / "a.cbl", tmp_path / "a.json"
    shutil.copy(COMMON_CBL, cbl)
    shutil.copy(FULL_JSON_CBL, json_cbl)
    before = json_cbl.read_bytes()
    code, _, err = cli_run(
        capsys, "rl", "convert", "--to", "json", "--overwrite", str(cbl), str(json_cbl)
    )
    assert code == 1
    assert f"{json_cbl}: is one of the inputs" in err
    assert json_cbl.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["a.cbl", "a.json"]


def test_convert_refuses_two_inputs_for_one_destination(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for folder in ("d1", "d2"):
        (tmp_path / folder).mkdir()
        shutil.copy(COMMON_CBL, tmp_path / folder / "x.cbl")
    output = tmp_path / "out"
    code, _, err = cli_run(
        capsys,
        "rl",
        "convert",
        "-o",
        str(output),
        str(tmp_path / "d1" / "x.cbl"),
        str(tmp_path / "d2" / "x.cbl"),
    )
    assert code == 1
    assert "would be written by 2 inputs" in err
    assert not output.exists()


def test_an_existing_file_is_kept_without_overwrite(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    taken = tmp_path / "common.yaml"
    taken.write_text("mine")
    argv = ("rl", "convert", "-o", str(tmp_path), str(COMMON_CBL))
    code, _, err = cli_run(capsys, *argv)
    assert code == 1
    assert f"{taken}: exists; --overwrite replaces it" in err
    assert taken.read_text() == "mine"
    assert cli_run(capsys, *argv[:2], "--overwrite", *argv[2:])[0] == 0
    assert load(taken).reading_list["name"] == "[Marvel] Civil War (Hand Written)"


def test_combine_output_is_checked_first(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    taken = tmp_path / "out.yaml"
    taken.write_text("mine")
    paths = (str(TWO_DATABASES_CBL), str(COMMON_CBL))
    code, out, err = cli_run(capsys, "rl", "combine", "-o", str(taken), *paths)
    assert (code, out) == (1, "")
    assert "exists; --overwrite replaces it" in err
    assert taken.read_text() == "mine"
    assert (
        cli_run(capsys, "rl", "combine", "--overwrite", "-o", str(taken), *paths)[0]
        == 0
    )
    assert len(load(taken).reading_list["entries"]) == 3
    # An input is never written over, even with --overwrite.
    copy = tmp_path / "copy.cbl"
    shutil.copy(COMMON_CBL, copy)
    code, _, err = cli_run(
        capsys,
        "rl",
        "combine",
        "--overwrite",
        "--to",
        "cbl",
        "-o",
        str(copy),
        str(copy),
        str(TWO_DATABASES_CBL),
    )
    assert code == 1
    assert "is one of the inputs" in err
    assert copy.read_bytes() == COMMON_CBL.read_bytes()


def _tag_arcs(path: Path, *names: str) -> None:
    from comicbox.readinglists import arc_patch
    from comicbox.write import write_metadata

    for name in names:
        write_metadata(path, arc_patch(name, 1), formats=["comicbox_json"])


def _arcs_output(tmp_path: Path) -> tuple[Path, Path]:
    """Tag a comic with two arcs whose names make one file name."""
    comics = tmp_path / "comics"
    comics.mkdir()
    shutil.copy(CIX_CBZ_SOURCE_PATH, comics / "a.cbz")
    _tag_arcs(comics / "a.cbz", "War/Peace", "War:Peace")
    return comics, tmp_path / "lists"


def test_from_arcs_never_writes_one_list_over_another(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    comics, output = _arcs_output(tmp_path)
    code, _, _ = cli_run(capsys, "rl", "from-arcs", "-o", str(output), str(comics))
    assert code == 0
    written = {path.name for path in output.iterdir()}
    assert {"War_Peace.yaml", "War_Peace 2.yaml"} <= written


def test_from_arcs_keeps_existing_files(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    comics, output = _arcs_output(tmp_path)
    args = ("rl", "from-arcs", "-o", str(output), str(comics))
    cli_run(capsys, *args)
    before = {path: path.read_bytes() for path in output.iterdir()}
    code, _, err = cli_run(capsys, *args)
    assert code == 1
    assert err.count("exists; --overwrite replaces it") == len(before)
    assert {path: path.read_bytes() for path in output.iterdir()} == before
    assert cli_run(capsys, *args[:2], "--overwrite", *args[2:])[0] == 0
    assert {path.name for path in output.iterdir()} == {path.name for path in before}


def test_stdout_carries_only_the_list(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Warnings, losses, the report and log lines all go to stderr."""
    from loguru import logger as comicbox_logger

    noisy = tmp_path / "noisy.yaml"
    noisy.write_text(
        "reading_list:\n  name: Civil War\n  descripton: x\n  entries:\n"  # codespell:ignore
        "    - series: {name: Civil War, start_year: 2006}\n"
        "      volume: {number: -1}\n      issue: {name: '1'}\n"
    )
    code = exit_code("rl", "combine", str(noisy), str(COMMON_CBL))
    comicbox_logger.warning("a log line")
    comicbox_logger.complete()
    captured = capsys.readouterr()
    assert code == 0
    assert loads(captured.out).reading_list["name"] == "Civil War"
    assert "a log line" in captured.err
    assert "read as 0" not in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ("convert", "-o", "{file}", str(COMMON_CBL)),
        ("combine", "-o", "{missing}/x.yaml", str(COMMON_CBL), str(TWO_DATABASES_CBL)),
        ("print", "{missing}"),
    ],
    ids=["output-is-a-file", "output-in-a-missing-dir", "missing-input"],
)
def test_file_errors_are_one_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, argv: tuple[str, ...]
) -> None:
    a_file = tmp_path / "a-file"
    a_file.write_text("")
    args = [arg.format(file=a_file, missing=tmp_path / "missing") for arg in argv]
    code = exit_code("rl", *args)
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1


def test_a_failed_write_leaves_no_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "list.yaml"

    def no_rename(*_args: object) -> None:
        reason = "disk full"
        raise OSError(reason)

    monkeypatch.setattr(type(destination), "replace", no_rename)
    with pytest.raises(OSError, match="disk full"):
        readinglist_cli.write_text(destination, "reading_list: {name: A}\n")
    assert list(tmp_path.iterdir()) == []


def test_files_are_written_as_utf8(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "pokemon.yaml"
    source.write_bytes("reading_list:\n  name: Pokémon ワンピース\n".encode())
    output = tmp_path / "o"
    code, _, _ = cli_run(capsys, "rl", "convert", "-o", str(output), str(source))
    assert code == 0
    text = (output / "pokemon.yaml").read_bytes().decode("utf-8")
    assert "Pokémon ワンピース" in text


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("key: [unclosed\n", "Not valid YAML: expected ',' or ']'"),
        ('{"a": }', "Not valid JSON: Expecting value at line 1, column 7."),
        ("<ReadingList><Name>x</Name>", "Not valid XML: no element found: line 1"),
        ("just: text\n", "Not a reading list in any format comicbox reads."),
    ],
    ids=["yaml", "json", "xml", "not-a-list"],
)
def test_a_syntax_error_says_what_and_where(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, text: str, message: str
) -> None:
    path = tmp_path / "junk.txt"
    path.write_text(text)
    code, _, err = cli_run(capsys, "rl", "print", str(path))
    assert code == 1
    assert message in err
    assert err.count(str(path)) == 1


def test_keyless_entries_are_counted(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    keyless = tmp_path / "keyless.yaml"
    keyless.write_text(
        "reading_list:\n  name: A\n  entries:\n"
        "    - series: {name: Civil War}\n      issue: {name: '1'}\n"
        "    - series: {name: Civil War}\n      issue: {name: '2'}\n"
    )
    for action in ("combine", "compare"):
        code, _, err = cli_run(capsys, "rl", action, str(keyless), str(COMMON_CBL))
        assert code == 0
        assert f"{keyless}: 2 entries have no key and match nothing" in err


def test_every_action_reports_what_a_read_dropped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad_year = tmp_path / "bad-year.cbl"
    bad_year.write_text(
        "<ReadingList><Name>A</Name><StartYear>abc</StartYear><Books>"
        "<Book Series='Batman' Number='1' Volume='1940' /></Books>"
        "<Matchers /></ReadingList>"
    )
    for argv in (
        ("combine", str(bad_year), str(COMMON_CBL)),
        ("compare", str(bad_year), str(COMMON_CBL)),
        ("convert", "-o", str(tmp_path / "out"), str(bad_year)),
    ):
        code, _, err = cli_run(capsys, "rl", *argv)
        assert code == 0
        assert f"{bad_year}: warning: ReadingList.StartYear: 'abc' dropped" in err


def test_one_keyless_entry_is_counted_in_the_singular(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    keyless = tmp_path / "keyless.yaml"
    keyless.write_text(
        "reading_list:\n  name: A\n  entries:\n"
        "    - series: {name: Civil War}\n      issue: {name: '1'}\n"
    )
    _, _, err = cli_run(capsys, "rl", "compare", str(keyless), str(COMMON_CBL))
    assert f"{keyless}: 1 entry has no key and matches nothing" in err


def test_validate_refuses_yaml_aliases_in_one_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "hostile.yaml"
    path.write_text("a: &a [x, x]\nb: [*a, *a]\nreading_list:\n  name: n\n")

    code, out, err = cli_run(capsys, "rl", "validate", str(path))

    assert code == 1
    assert "YAML aliases" in out
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    "text",
    [
        '{"reading_list": ' + "[" * 200_000 + "]" * 200_000 + "}",
        '{"reading_list": {"name": "x", "notes": '
        + "[" * 200_000
        + "]" * 200_000
        + "}}",
    ],
    ids=["root", "notes"],
)
def test_validate_reports_deep_nesting_in_one_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, text: str
) -> None:
    """
    Never a RecursionError, whatever the stack allows the parser.

    Under ``make``'s 64 MiB stack the JSON parses, and it was the schema
    error's message, pretty-printing the value, that recursed.
    """
    path = tmp_path / "deep.json"
    path.write_text(text)

    code, out, err = cli_run(capsys, "rl", "validate", str(path))

    assert code == 1
    assert "✗" in out
    assert "Traceback" not in out + err


def test_combine_reports_an_id_left_on_two_entries(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    a = tmp_path / "a.yaml"
    a.write_text(
        "reading_list:\n  name: A\n  entries:\n"
        "    - series: {name: X}\n      issue: {name: '1'}\n"
        "      identifiers: {comicvine: {key: cv1}, grandcomicsdatabase: {key: g1}}\n"
    )
    b = tmp_path / "b.yaml"
    b.write_text(
        "reading_list:\n  name: B\n  entries:\n"
        "    - series: {name: X}\n      issue: {name: '1'}\n"
        "      identifiers: {grandcomicsdatabase: {key: g1}}\n"
        "    - series: {name: X}\n      issue: {name: '1'}\n"
        "      identifiers: {comicvine: {key: cv1}}\n"
    )

    code, _, err = cli_run(capsys, "rl", "combine", str(a), str(b))

    assert code == 0
    assert "shared id: " in err
    assert "is on entries #1, #2" in err
