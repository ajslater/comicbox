"""
``comicbox rl match``: which comics are each entry's, and why.

Every comic is generated under tmp_path. The write-arcs tests that
share its fixtures are in the ``test_cli_readinglist_write_arcs*``
modules.
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import TYPE_CHECKING

import pytest

from comicbox.readinglists import library as library_module
from tests.util.comics import digests, make_comic
from tests.util.readinglist_cli import (
    flat,
    rl_main,
    rl_run,
    rl_write,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


def test_match_shows_what_is_had_and_missing(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, err = rl_run(capsys, "match", str(reading_list), str(library))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    assert "1 Crimson Tide 2006 1 cw1.cbz name" in rows
    assert "2 Crimson Tide 2006 2 missing" in rows
    assert "3 Amazing Snail-Man 1963 532 asm532.cbz variant" in rows
    assert "2 of 4 entries found in 3 comics; 2 missing." in err


def test_each_comic_of_an_entry_is_a_row(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    make_comic(
        library / "copy" / "cw1.cbz", series="Crimson Tide", number="1", start_year=2006
    )

    _, out, _ = rl_run(capsys, "match", str(reading_list), str(library))

    rows = [" ".join(line.split()) for line in out.splitlines()]
    first = rows.index("1 Crimson Tide 2006 1 copy/cw1.cbz name")
    assert rows[first + 1] == "cw1.cbz name"


def test_a_cover_year_match_is_its_own_kind(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """No id, start year or volume on either side: series, issue and year."""
    listed = tmp_path / "bladehawk.yaml"
    listed.write_text(
        "reading_list:\n  name: Bladehawk\n  entries:\n"
        "    - series: {name: Bladehawk}\n      issue: {name: '1'}\n"
        "      date: {year: 2016}\n"
        "    - series: {name: Bladehawk}\n      issue: {name: '2'}\n"
    )
    comics = tmp_path / "comics"
    make_comic(
        comics / "bladehawk.cbz",
        series="Bladehawk",
        number="1",
        cover_date="2016-08-01",
    )

    code, out, err = rl_run(capsys, "match", str(listed), str(comics))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    assert "1 Bladehawk 1 bladehawk.cbz name-year" in rows
    # Only the entry with no year is counted as having no key.
    assert "1 entry has no key and matches nothing" in err


_ARDENT = (
    "reading_list:\n  name: Ardent Firsts\n  entries:\n"
    "    - series: {name: Ardent}\n      issue: {name: '1'}\n"
    "      date: {year: 2016}\n"
)


def _volumes(directory: Path, *start_years: int | None) -> list[Path]:
    """Make Ardent #1 dated 2016 in each volume given; None has no start year."""
    return [
        make_comic(
            directory / f"{index}-ardent-{start_year}.cbz",
            series="Ardent",
            number="1",
            start_year=start_year,
            cover_date="2016-08-01",
        )
        for index, start_year in enumerate(start_years)
    ]


def test_an_entry_that_fits_two_volumes_is_listed_and_never_tagged(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    listed = tmp_path / "ardent.yaml"
    listed.write_text(_ARDENT)
    comics = tmp_path / "comics"
    paths = _volumes(comics, 2011, 2016)
    before = digests(comics)

    _, matched, _ = rl_run(capsys, "match", str(listed), str(comics))
    _, dry, dry_err = rl_write(capsys, str(listed), str(comics))
    code, out, err = rl_write(capsys, str(listed), str(comics), apply=True)

    assert flat(matched).count("(ambiguous: the 2011 and 2016 volumes)") == 2
    reason = (
        "not written: entry #1 fits the 2011 and 2016 volumes alike;"
        " a start year on the entry settles it"
    )
    for text in (dry, out):
        assert all(f"{path} {reason}" in flat(text) for path in paths)
    assert code == 1
    assert digests(comics) == before
    assert "2 comics not written, for an entry that fits more than one volume." in err
    assert "Dry run: 0 of 0 matched comics would change" in dry_err


def test_a_cover_year_match_of_another_volume_is_not_a_match(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Beside the id's 2016 comic, the 2011 comic is neither listed nor tagged."""
    listed = tmp_path / "ardent.yaml"
    listed.write_text(_ARDENT + "      identifiers: {comicvine: {key: '7'}}\n")
    comics = tmp_path / "comics"
    v2011 = _volumes(comics, 2011)[0]
    v2016 = make_comic(
        comics / "id-ardent-2016.cbz",
        series="Ardent",
        number="1",
        start_year=2016,
        cover_date="2016-08-01",
        ids={"comicvine": "7"},
    )
    untouched = v2011.read_bytes()

    _, matched, _ = rl_run(capsys, "match", str(listed), str(comics))
    code, out, _ = rl_write(capsys, str(listed), str(comics), apply=True)

    assert v2011.name not in matched
    assert code == 0
    assert f"{v2016} added 'Ardent Firsts' #1" in flat(out)
    assert v2011.name not in out
    assert v2011.read_bytes() == untouched


def test_a_volume_number_entry_tags_its_comic_and_not_two_other_volumes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    listed = tmp_path / "ardent.yaml"
    listed.write_text(_ARDENT.replace("issue:", "volume: {number: 2}\n      issue:"))
    comics = tmp_path / "comics"
    others = _volumes(comics, 2011, 2016)
    vol2 = make_comic(
        comics / "vol2-ardent.cbz",
        series="Ardent",
        number="1",
        volume=2,
        cover_date="2016-08-01",
    )

    untouched = {path: path.read_bytes() for path in others}

    _, matched, _ = rl_run(capsys, "match", str(listed), str(comics))
    code, out, _ = rl_write(capsys, str(listed), str(comics), apply=True)

    # R3-J: the volume-2 comic is the entry's exact comic, so the comics of
    # the other two volumes are not found beside it at all.
    assert "ambiguous" not in matched
    assert all(path.name not in matched for path in others)
    assert code == 0
    assert f"{vol2} added 'Ardent Firsts' #1" in flat(out)
    assert {path: path.read_bytes() for path in others} == untouched


@pytest.mark.parametrize(
    ("start_years", "tagged"),
    [
        # Copies of one volume.
        ((2016, 2016), (0, 1)),
        # A comic with no start year beside a comic of one volume: it is the
        # entry's exact comic, so only it is tagged (R3-J).
        ((2016, None), (1,)),
    ],
)
def test_comics_of_one_volume_are_tagged(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    start_years: tuple[int | None, ...],
    tagged: tuple[int, ...],
) -> None:
    listed = tmp_path / "ardent.yaml"
    listed.write_text(_ARDENT)
    comics = tmp_path / "comics"
    paths = _volumes(comics, *start_years)

    _, matched, _ = rl_run(capsys, "match", str(listed), str(comics))
    code, out, _ = rl_write(capsys, str(listed), str(comics), apply=True)

    assert "ambiguous" not in matched
    assert code == 0
    added = [i for i, path in enumerate(paths) if f"{path} added" in flat(out)]
    assert tuple(added) == tagged


def test_match_output_that_is_not_a_terminal_is_not_wrapped(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    deep = tmp_path / "comics" / ("a-long-directory-name-" * 4) / "crimson-tide"
    make_comic(deep / "cw1.cbz", series="Crimson Tide", number="1", start_year=2006)

    _, out, _ = rl_run(capsys, "match", str(reading_list), str(tmp_path / "comics"))

    (row,) = [line for line in out.splitlines() if "cw1.cbz" in line]
    assert len(row.rstrip()) > 80
    assert row.split()[-1] == "name"


def test_a_directory_with_no_comics(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    code, out, err = rl_run(capsys, "match", str(reading_list), str(empty))

    assert code == 0
    assert f"No tagged comics in {empty}." in err
    assert out.count("missing") == 4


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_a_directory_that_cannot_be_read_is_a_warning(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    locked = library / "locked"
    make_comic(locked / "cw2.cbz", series="Crimson Tide", number="2", start_year=2006)
    locked.chmod(0)
    try:
        code, out, err = rl_run(capsys, "match", str(reading_list), str(library))
    finally:
        locked.chmod(0o755)

    assert code == 1
    assert f"warning: {locked}: Permission denied; not searched" in err
    assert "No tagged comics" not in err
    assert "cw1.cbz" in out


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_a_top_directory_that_cannot_be_read_is_a_warning(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    library.chmod(0)
    try:
        code, _, err = rl_run(capsys, "match", str(reading_list), str(library))
    finally:
        library.chmod(0o755)

    assert code == 1
    assert "Permission denied; not searched" in err
    assert "No tagged comics" not in err


def test_a_linked_directory_is_not_searched(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    make_comic(
        elsewhere / "cw1.cbz", series="Crimson Tide", number="1", start_year=2006
    )
    comics = tmp_path / "comics"
    comics.mkdir()
    (comics / "linked").symlink_to(elsewhere, target_is_directory=True)

    _, out, _ = rl_run(capsys, "match", str(reading_list), str(comics))

    assert "cw1.cbz" not in out


@pytest.fixture
def spawned_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Start the reader's workers afresh, so their stderr is this test's.

    Linux's default forkserver forks them from a server an earlier test
    started, and they write to that test's stderr, which capfd never sees.
    """
    spawn = multiprocessing.get_context("spawn")
    monkeypatch.setattr(
        library_module,
        "ProcessPoolExecutor",
        partial(ProcessPoolExecutor, mp_context=spawn),
    )


@pytest.mark.usefixtures("spawned_workers")
def test_a_corrupt_comic_is_one_line_and_the_rest_are_read(
    capfd: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    """The reader's workers print nothing of their own about it."""
    (library / "bad.cbz").write_bytes(b"not a zip at all")

    code = rl_main("match", str(reading_list), str(library))

    out, err = capfd.readouterr()
    assert code == 1
    (line,) = [line for line in err.splitlines() if "bad.cbz" in line]
    assert line.startswith(f"{library / 'bad.cbz'}: Unsupported archive type")
    assert "Traceback" not in err
    assert "cw1.cbz" in out


def test_match_needs_a_directory(
    capsys: pytest.CaptureFixture[str], reading_list: Path
) -> None:
    code, _, err = rl_run(capsys, "match", str(reading_list), str(reading_list))
    assert code == 1
    assert "not a directory" in err


def test_match_marks_a_comic_with_an_unreadable_tag_file(
    capsys: pytest.CaptureFixture[str], bladehawk_list: Path, unreadable: Path
) -> None:
    _, out, _ = rl_run(capsys, "match", str(bladehawk_list), str(unreadable.parent))
    assert f"{unreadable.name} (unreadable ComicInfo.xml)" in flat(out)


@pytest.mark.usefixtures("spawned_workers")
def test_worker_warnings_honour_quiet(
    capfd: pytest.CaptureFixture[str], bladehawk_list: Path, unreadable: Path
) -> None:
    directory = str(unreadable.parent)
    rl_main("match", str(bladehawk_list), directory)
    loud = capfd.readouterr().err
    rl_main("-QQ", "match", str(bladehawk_list), directory)
    quiet = capfd.readouterr().err

    # Once: looking for unreadable tag files must not warn of them again.
    assert loud.count("Unable to load") == 1
    assert "Unable to load" not in quiet


def test_a_missing_entry_shows_the_comics_it_refused(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Another volume of one cover year, and one name off by its cover year."""
    reading_list = tmp_path / "bladehawk.yaml"
    reading_list.write_text(
        """reading_list:
  name: Bladehawk
  entries:
    - series: {name: Bladehawk, start_year: 2016}
      issue: {name: '1'}
      date: {cover_date: 2016-06-01}
    - series: {name: Bladehawk, start_year: 2011}
      issue: {name: '2'}
      date: {cover_date: 2011-12-01}
"""
    )
    comics = tmp_path / "comics"
    make_comic(
        comics / "b2011-1.cbz",
        series="Bladehawk",
        number="1",
        start_year=2011,
        cover_date="2016-06-01",
    )
    make_comic(
        comics / "b2011-2.cbz",
        series="Bladehawk",
        number="2",
        start_year=2011,
        cover_date="2015-01-01",
    )

    code, out, err = rl_run(capsys, "match", str(reading_list), str(comics))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    first = rows.index("1 Bladehawk 2016 1 missing")
    assert rows[first + 1] == "b2011-1.cbz (other-volume) refused"
    second = rows.index("2 Bladehawk 2011 2 missing")
    assert rows[second + 1] == "b2011-2.cbz (cover-year) refused"
    assert "0 of 2 entries found in 2 comics; 2 missing." in err
