"""
``comicbox rl match`` and ``comicbox rl write-arcs``.

Every comic here is generated under tmp_path: write-arcs changes comics, so
no test points it at anything else.
"""

from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger as loguru_logger

from comicbox import cli, logger
from comicbox.readinglists.match import read_comics
from comicbox.write import WriteResult
from tests.util.comics import digests, make_comic

if TYPE_CHECKING:
    import threading
    from collections.abc import Iterator
    from pathlib import Path

_LIST = """reading_list:
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


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


@pytest.fixture
def reading_list(tmp_path: Path) -> Path:
    path = tmp_path / "civil-war.yaml"
    path.write_text(_LIST)
    return path


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Two of the list's issues, one by a variant name, and one it lacks."""
    directory = tmp_path / "comics"
    make_comic(directory / "cw1.cbz", series="Civil War", number="1", start_year=2006)
    make_comic(
        directory / "asm532.cbz",
        series="The Amazing Spider-Man",
        number="532",
        start_year=1963,
    )
    make_comic(directory / "other.cbz", series="Saga", number="1", start_year=2012)
    return directory


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = 0
    try:
        cli.main(("comicbox", "rl", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, " ".join(captured.err.split())


def _arcs(directory: Path) -> dict[str, Any]:
    return {
        path.name: tags.get("arcs") for path, tags in read_comics(directory).items()
    }


# ----------------------------------------------------------------- match


def test_match_shows_what_is_had_and_missing(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, err = _run(capsys, "match", str(reading_list), str(library))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    assert any(row.startswith("1 Civil War 2006 1 cw1.cbz name") for row in rows)
    assert any(row.startswith("2 Civil War 2006 2 missing") for row in rows)
    assert any("asm532.cbz variant" in row for row in rows)
    assert "2 of 4 entries found in 3 comics; 2 missing." in err


def test_two_files_of_one_issue_are_both_listed(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    make_comic(
        library / "copy" / "cw1.cbz", series="Civil War", number="1", start_year=2006
    )

    _, out, _ = _run(capsys, "match", str(reading_list), str(library))

    assert "copy/cw1.cbz" in out
    assert "cw1.cbz" in out.replace("copy/cw1.cbz", "")


def test_a_directory_with_no_comics(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    code, out, err = _run(capsys, "match", str(reading_list), str(empty))

    assert code == 0
    assert f"No tagged comics in {empty}." in err
    assert out.count("missing") == 4


def test_a_corrupt_comic_is_one_line_and_the_rest_are_read(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    (library / "bad.cbz").write_bytes(b"not a zip at all")

    code, out, err = _run(capsys, "match", str(reading_list), str(library))

    assert code == 1
    assert "bad.cbz" in err
    assert "Traceback" not in err
    assert "cw1.cbz" in out


def test_match_needs_a_directory(
    capsys: pytest.CaptureFixture[str], reading_list: Path
) -> None:
    code, _, err = _run(capsys, "match", str(reading_list), str(reading_list))
    assert code == 1
    assert "not a directory" in err


# ------------------------------------------------------------ write-arcs


def test_a_dry_run_changes_no_byte(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, out, err = _run(
        capsys, "write-arcs", "-w", "json", str(reading_list), str(library)
    )

    assert code == 0
    assert digests(library) == before
    assert "cw1.cbz would add 'Civil War' #1" in " ".join(out.split())
    assert "asm532.cbz would add 'Civil War' #3" in " ".join(out.split())
    assert "Dry run: 2 of 2 matched comics would change; --apply writes them." in err


def test_apply_writes_the_arcs(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, _ = _run(
        capsys, "write-arcs", "--apply", "-w", "json", str(reading_list), str(library)
    )

    assert code == 0
    assert "added 'Civil War' #1" in " ".join(out.split())
    assert _arcs(library) == {
        "asm532.cbz": {"Civil War": {"number": 3}},
        "cw1.cbz": {"Civil War": {"number": 1}},
        "other.cbz": None,
    }


def test_a_comic_already_tagged_is_left_alone(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    same = make_comic(
        directory / "cw1.cbz",
        series="Civil War",
        number="1",
        start_year=2006,
        arcs={"Civil War": 1},
    )
    make_comic(
        directory / "cw2.cbz",
        series="Civil War",
        number="2",
        start_year=2006,
        arcs={"Civil War": 9, "Other": 1},
    )
    untouched = same.read_bytes()

    code, out, _ = _run(
        capsys, "write-arcs", "--apply", "-w", "json", str(reading_list), str(directory)
    )

    assert code == 0
    flat = " ".join(out.split())
    assert "cw1.cbz: already has 'Civil War' #1; left alone" in flat
    assert "cw2.cbz renumbered 'Civil War' #2, was #9" in flat
    assert same.read_bytes() == untouched
    assert _arcs(directory)["cw2.cbz"] == {
        "Civil War": {"number": 2},
        "Other": {"number": 1},
    }


def test_a_dry_run_reports_a_different_number(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    make_comic(
        directory / "cw2.cbz",
        series="Civil War",
        number="2",
        start_year=2006,
        arcs={"Civil War": 9},
    )
    before = digests(directory)

    _, out, _ = _run(
        capsys, "write-arcs", "-w", "json", str(reading_list), str(directory)
    )

    assert "cw2.cbz would renumber 'Civil War' #2, was #9" in " ".join(out.split())
    assert digests(directory) == before


def test_write_arcs_needs_formats(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, _, err = _run(capsys, "write-arcs", str(reading_list), str(library))
    assert code == 2
    assert "-w/--write" in err


def test_an_unknown_format_writes_nothing(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, _, err = _run(
        capsys,
        "write-arcs",
        "--apply",
        "-w",
        "nonsense",
        str(reading_list),
        str(library),
    )

    assert code == 1
    assert "-w names no format comicbox writes" in err
    assert digests(library) == before


def test_a_read_only_comic_fails_and_the_rest_are_written(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    locked = library / "cw1.cbz"
    locked.chmod(0o444)
    untouched = locked.read_bytes()
    try:
        code, out, err = _run(
            capsys,
            "write-arcs",
            "--apply",
            "-w",
            "json",
            str(reading_list),
            str(library),
        )
    finally:
        locked.chmod(0o644)

    assert code == 1
    assert "cw1.cbz: Permission denied" in err
    assert locked.read_bytes() == untouched
    assert "asm532.cbz added 'Civil War' #3" in " ".join(out.split())


def test_a_list_without_a_name_names_no_arc(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, library: Path
) -> None:
    nameless = tmp_path / "nameless.yaml"
    nameless.write_text(
        "reading_list:\n  entries:\n"
        "    - series: {name: Civil War, start_year: 2006}\n      issue: {name: '1'}\n"
    )

    code, _, err = _run(capsys, "write-arcs", "-w", "json", str(nameless), str(library))

    assert code == 1
    assert "the list has no name to tag its arc with" in err


def test_ctrl_c_stops_the_writes_not_under_way(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reading_list: Path,
    library: Path,
) -> None:
    """The first write lands, Ctrl-C comes, the rest are cancelled."""
    import comicbox.write

    def interrupted(items: Any, *, cancel: threading.Event, **_kwargs: Any) -> Any:
        items = list(items)
        yield WriteResult(items[0].path, written=True, final_path=items[0].path)
        os.kill(os.getpid(), signal.SIGINT)
        if not cancel.wait(10):
            reason = "never cancelled"
            raise AssertionError(reason)
        for item in items[1:]:
            yield WriteResult(item.path, cancelled=True)

    monkeypatch.setattr(comicbox.write, "bulk_write", interrupted)

    code, out, err = _run(
        capsys, "write-arcs", "--apply", "-w", "json", str(reading_list), str(library)
    )

    flat = " ".join(out.split())
    assert code == 130
    assert "added 'Civil War'" in flat
    assert "not written: cancelled" in flat
    assert "Stopping after the writes under way" in err
    assert err.endswith("Cancelled.")


def test_one_failed_write_does_not_stop_the_rest(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reading_list: Path,
    library: Path,
) -> None:
    """With stop_on_error, bulk_write cancels the rest after a failure."""
    import comicbox.write

    def first_fails(items: Any, *, stop_on_error: bool = False, **_kwargs: Any) -> Any:
        items = list(items)
        yield WriteResult(items[0].path, error=PermissionError(13, "Permission denied"))
        for item in items[1:]:
            if stop_on_error:
                yield WriteResult(item.path, cancelled=True)
            else:
                yield WriteResult(item.path, written=True, final_path=item.path)

    monkeypatch.setattr(comicbox.write, "bulk_write", first_fails)

    code, out, err = _run(
        capsys, "write-arcs", "--apply", "-w", "json", str(reading_list), str(library)
    )

    assert code == 1
    assert "asm532.cbz: Permission denied" in err
    assert "cw1.cbz added 'Civil War' #1" in " ".join(out.split())


def test_a_corrupt_comic_is_reported_once(library: Path) -> None:
    """The reader logged it too, so one failure took two lines."""
    (library / "bad.cbz").write_bytes(b"not a zip at all")
    logged: list[str] = []
    handler = loguru_logger.add(logged.append, level="WARNING", format="{message}")
    errors: list[Path] = []
    try:
        comics = read_comics(library, on_error=lambda path, _error: errors.append(path))
    finally:
        loguru_logger.remove(handler)

    assert errors == [library / "bad.cbz"]
    assert not [message for message in logged if "bad.cbz" in message]
    assert len(comics) == 3
