"""
``comicbox readinglist`` and ``comicbox rl`` through the real CLI entry point.

Like the doctor, a special first argument that `cli.main` sniffs before
building a normal run; unlike it, a parser of its own with subcommands.
"""

from __future__ import annotations

import contextlib
import json
import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from comicbox.readinglists import ReadingListFormats, load, loads
from comicbox.readinglists import cli as readinglist_cli
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
    assert "Not a reading list in any format" in out


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
    assert "lost: entries.date.cover_date" in err
    result = load(tmp_path / "common.json")
    assert result.fmt is ReadingListFormats.JSON_CBL
    assert len(result.reading_list["entries"]) == 3


def test_convert_never_overwrites_its_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    source = tmp_path / "list.json"
    shutil.copy(FULL_JSON_CBL, source)
    before = source.read_text()
    code, _, err = _run(capsys, "rl", "convert", "--to", "json", str(source))
    assert code == 1
    assert "is one of the inputs" in err
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


def test_validate_prints_what_a_read_drops(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    typo = tmp_path / "typo.yaml"
    misspelled = "descripton"  # codespell:ignore
    typo.write_text(CIVIL_WAR.read_text().replace("description:", f"{misspelled}:"))
    code, out, _ = _run(capsys, "rl", "validate", str(typo))
    assert code == 0
    assert f"warning: {misspelled}: 'The superhuman registration act" in out


def test_convert_writes_nothing_when_a_destination_is_an_input(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """a.cbl would become a.json, which is the other input."""
    cbl, json_cbl = tmp_path / "a.cbl", tmp_path / "a.json"
    shutil.copy(COMMON_CBL, cbl)
    shutil.copy(FULL_JSON_CBL, json_cbl)
    before = json_cbl.read_bytes()
    code, _, err = _run(
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
    code, _, err = _run(
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
    code, _, err = _run(capsys, *argv)
    assert code == 1
    assert f"{taken}: exists; --overwrite replaces it" in err
    assert taken.read_text() == "mine"
    assert _run(capsys, *argv[:2], "--overwrite", *argv[2:])[0] == 0
    assert load(taken).reading_list["name"] == "[Marvel] Civil War (Hand Written)"


def test_combine_output_is_checked_first(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    taken = tmp_path / "out.yaml"
    taken.write_text("mine")
    paths = (str(TWO_DATABASES_CBL), str(COMMON_CBL))
    code, out, err = _run(capsys, "rl", "combine", "-o", str(taken), *paths)
    assert (code, out) == (1, "")
    assert "exists; --overwrite replaces it" in err
    assert taken.read_text() == "mine"
    assert (
        _run(capsys, "rl", "combine", "--overwrite", "-o", str(taken), *paths)[0] == 0
    )
    assert len(load(taken).reading_list["entries"]) == 3
    # An input is never written over, even with --overwrite.
    copy = tmp_path / "copy.cbl"
    shutil.copy(COMMON_CBL, copy)
    code, _, err = _run(
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
    code, _, _ = _run(capsys, "rl", "from-arcs", "-o", str(output), str(comics))
    assert code == 0
    written = {path.name for path in output.iterdir()}
    assert {"War_Peace.yaml", "War_Peace 2.yaml"} <= written


def test_from_arcs_keeps_existing_files(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    comics, output = _arcs_output(tmp_path)
    args = ("rl", "from-arcs", "-o", str(output), str(comics))
    _run(capsys, *args)
    before = {path: path.read_bytes() for path in output.iterdir()}
    code, _, err = _run(capsys, *args)
    assert code == 1
    assert err.count("exists; --overwrite replaces it") == len(before)
    assert {path: path.read_bytes() for path in output.iterdir()} == before
    assert _run(capsys, *args[:2], "--overwrite", *args[2:])[0] == 0
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
    code = 0
    try:
        cli.main(("comicbox", "rl", "combine", str(noisy), str(COMMON_CBL)))
    except SystemExit as exc:
        code = int(exc.code or 0)
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
    code = 0
    try:
        cli.main(("comicbox", "rl", *args))
    except SystemExit as exc:
        code = int(exc.code or 0)
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
    code, _, _ = _run(capsys, "rl", "convert", "-o", str(output), str(source))
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
    code, _, err = _run(capsys, "rl", "print", str(path))
    assert code == 1
    assert message in err
    assert err.count(str(path)) == 1


def test_the_title_is_not_wrapped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    name = "A Reading List With A Rather Long Name Of Fifty Chars"
    path = tmp_path / "long.yaml"
    path.write_text(f"reading_list:\n  name: {name}\n  notes: n\n")
    with contextlib.suppress(SystemExit):
        cli.main(("comicbox", "rl", "print", str(path)))
    assert name in capsys.readouterr().out.splitlines()


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
        code, _, err = _run(capsys, "rl", action, str(keyless), str(COMMON_CBL))
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
        code, _, err = _run(capsys, "rl", *argv)
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
    _, _, err = _run(capsys, "rl", "compare", str(keyless), str(COMMON_CBL))
    assert f"{keyless}: 1 entry has no key and matches nothing" in err


def test_validate_refuses_yaml_aliases_in_one_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "hostile.yaml"
    path.write_text("a: &a [x, x]\nb: [*a, *a]\nreading_list:\n  name: n\n")

    code, out, err = _run(capsys, "rl", "validate", str(path))

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

    code, out, err = _run(capsys, "rl", "validate", str(path))

    assert code == 1
    assert "✗" in out
    assert "Traceback" not in out + err
