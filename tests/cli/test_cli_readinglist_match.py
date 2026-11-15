"""
``comicbox rl match`` and ``comicbox rl write-arcs``.

Every comic here is generated under tmp_path, or copied there from
tests/files: write-arcs changes comics, so no test points it at anything
else. Every write goes through the real ``bulk_write``.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from comicbox import cli, logger
from comicbox.box import Comicbox
from comicbox.readinglists.library import read_comics
from tests.const import (
    CB7_SOURCE_PATH,
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_PDF_SOURCE_PATH,
    PDF_SOURCE_PATH,
)
from tests.util.comics import JSON, digests, make_comic, tag_files

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"

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
    """Restore logging, and Ctrl-C, which a cancelled command leaves ignored."""
    handler = signal.getsignal(signal.SIGINT)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, handler)
        logger._initialized_key = None
        logger.init_logging()


def _write_list(path: Path, name: str = "Civil War", body: str = _LIST) -> Path:
    path.write_text(
        body.replace("name: Civil War\n  entries", f"name: {name}\n  entries")
    )
    return path


@pytest.fixture
def reading_list(tmp_path: Path) -> Path:
    return _write_list(tmp_path / "civil-war.yaml")


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


def _main(*argv: str) -> int:
    try:
        cli.main(("comicbox", "rl", *argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = _main(*argv)
    captured = capsys.readouterr()
    return code, captured.out, " ".join(captured.err.split())


def _flat(text: str) -> str:
    return " ".join(text.split())


def _arcs(directory: Path) -> dict[str, Any]:
    return {
        path.name: comic.tags.get("arcs")
        for path, comic in read_comics(directory).comics.items()
    }


def _tags(path: Path) -> dict[str, Any]:
    with Comicbox(path) as box:
        return dict(box.to_dict()["comicbox"])


def _write(
    capsys: pytest.CaptureFixture[str], *argv: str, apply: bool = False
) -> tuple[int, str, str]:
    """Run write-arcs, with -w json unless the test gives its own -w."""
    options = ["--apply"] if apply else []
    if "-w" not in argv:
        options += ["-w", "json"]
    return _run(capsys, "write-arcs", *options, *argv)


# ----------------------------------------------------------------- match


def test_match_shows_what_is_had_and_missing(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, err = _run(capsys, "match", str(reading_list), str(library))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    assert "1 Civil War 2006 1 cw1.cbz name" in rows
    assert "2 Civil War 2006 2 missing" in rows
    assert "3 Amazing Spider-Man 1963 532 asm532.cbz variant" in rows
    assert "2 of 4 entries found in 3 comics; 2 missing." in err


def test_each_comic_of_an_entry_is_a_row(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    make_comic(
        library / "copy" / "cw1.cbz", series="Civil War", number="1", start_year=2006
    )

    _, out, _ = _run(capsys, "match", str(reading_list), str(library))

    rows = [" ".join(line.split()) for line in out.splitlines()]
    first = rows.index("1 Civil War 2006 1 copy/cw1.cbz name")
    assert rows[first + 1] == "cw1.cbz name"


def test_a_cover_year_match_is_its_own_kind(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """No id, start year or volume on either side: series, issue and year."""
    listed = tmp_path / "batman.yaml"
    listed.write_text(
        "reading_list:\n  name: Batman\n  entries:\n"
        "    - series: {name: Batman}\n      issue: {name: '1'}\n"
        "      date: {year: 2016}\n"
        "    - series: {name: Batman}\n      issue: {name: '2'}\n"
    )
    comics = tmp_path / "comics"
    make_comic(
        comics / "batman.cbz", series="Batman", number="1", cover_date="2016-08-01"
    )

    code, out, err = _run(capsys, "match", str(listed), str(comics))

    assert code == 0
    rows = [" ".join(line.split()) for line in out.splitlines()]
    assert "1 Batman 1 batman.cbz name-year" in rows
    # Only the entry with no year is counted as having no key.
    assert "1 entry has no key and matches nothing" in err


_AVENGERS = (
    "reading_list:\n  name: Avengers Firsts\n  entries:\n"
    "    - series: {name: Avengers}\n      issue: {name: '1'}\n"
    "      date: {year: 2016}\n"
)


def _volumes(directory: Path, *start_years: int | None) -> list[Path]:
    """Make Avengers #1 dated 2016 in each volume given; None has no start year."""
    return [
        make_comic(
            directory / f"{index}-avengers-{start_year}.cbz",
            series="Avengers",
            number="1",
            start_year=start_year,
            cover_date="2016-08-01",
        )
        for index, start_year in enumerate(start_years)
    ]


def test_an_entry_that_fits_two_volumes_is_listed_and_never_tagged(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    listed = tmp_path / "avengers.yaml"
    listed.write_text(_AVENGERS)
    comics = tmp_path / "comics"
    paths = _volumes(comics, 2011, 2016)
    before = digests(comics)

    _, matched, _ = _run(capsys, "match", str(listed), str(comics))
    _, dry, dry_err = _write(capsys, str(listed), str(comics))
    code, out, err = _write(capsys, str(listed), str(comics), apply=True)

    assert _flat(matched).count("(ambiguous: the 2011 and 2016 volumes)") == 2
    reason = (
        "not written: entry #1 fits the 2011 and 2016 volumes alike;"
        " a start year on the entry settles it"
    )
    for text in (dry, out):
        assert all(f"{path} {reason}" in _flat(text) for path in paths)
    assert code == 1
    assert digests(comics) == before
    assert "2 comics not written, for an entry that fits more than one volume." in err
    assert "Dry run: 0 of 0 matched comics would change" in dry_err


@pytest.mark.parametrize(
    "start_years",
    [
        # Copies of one volume.
        (2016, 2016),
        # A comic with no start year beside comics of one volume.
        (2016, None),
    ],
)
def test_comics_of_one_volume_are_tagged(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    start_years: tuple[int | None, ...],
) -> None:
    listed = tmp_path / "avengers.yaml"
    listed.write_text(_AVENGERS)
    comics = tmp_path / "comics"
    paths = _volumes(comics, *start_years)

    _, matched, _ = _run(capsys, "match", str(listed), str(comics))
    code, out, _ = _write(capsys, str(listed), str(comics), apply=True)

    assert "ambiguous" not in matched
    assert code == 0
    assert all(f"{path} added 'Avengers Firsts' #1" in _flat(out) for path in paths)


def test_match_output_that_is_not_a_terminal_is_not_wrapped(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    deep = tmp_path / "comics" / ("a-long-directory-name-" * 4) / "civil-war"
    make_comic(deep / "cw1.cbz", series="Civil War", number="1", start_year=2006)

    _, out, _ = _run(capsys, "match", str(reading_list), str(tmp_path / "comics"))

    (row,) = [line for line in out.splitlines() if "cw1.cbz" in line]
    assert len(row.rstrip()) > 80
    assert row.split()[-1] == "name"


def test_a_directory_with_no_comics(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    code, out, err = _run(capsys, "match", str(reading_list), str(empty))

    assert code == 0
    assert f"No tagged comics in {empty}." in err
    assert out.count("missing") == 4


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_a_directory_that_cannot_be_read_is_a_warning(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    locked = library / "locked"
    make_comic(locked / "cw2.cbz", series="Civil War", number="2", start_year=2006)
    locked.chmod(0)
    try:
        code, out, err = _run(capsys, "match", str(reading_list), str(library))
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
        code, _, err = _run(capsys, "match", str(reading_list), str(library))
    finally:
        library.chmod(0o755)

    assert code == 1
    assert "Permission denied; not searched" in err
    assert "No tagged comics" not in err


def test_a_linked_directory_is_not_searched(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    make_comic(elsewhere / "cw1.cbz", series="Civil War", number="1", start_year=2006)
    comics = tmp_path / "comics"
    comics.mkdir()
    (comics / "linked").symlink_to(elsewhere, target_is_directory=True)

    _, out, _ = _run(capsys, "match", str(reading_list), str(comics))

    assert "cw1.cbz" not in out


def test_a_corrupt_comic_is_one_line_and_the_rest_are_read(
    capfd: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    """The reader's workers print nothing of their own about it."""
    (library / "bad.cbz").write_bytes(b"not a zip at all")

    code = _main("match", str(reading_list), str(library))

    out, err = capfd.readouterr()
    assert code == 1
    (line,) = [line for line in err.splitlines() if "bad.cbz" in line]
    assert line.startswith(f"{library / 'bad.cbz'}: Unsupported archive type")
    assert "Traceback" not in err
    assert "cw1.cbz" in out


def test_match_needs_a_directory(
    capsys: pytest.CaptureFixture[str], reading_list: Path
) -> None:
    code, _, err = _run(capsys, "match", str(reading_list), str(reading_list))
    assert code == 1
    assert "not a directory" in err


# A ComicInfo.xml with a raw "&", which no XML parser reads.
_BROKEN_CIX = "<ComicInfo><Series>Batman & Robin</Series><Number>1</Number></ComicInfo>"


@pytest.fixture
def unreadable(tmp_path: Path) -> Path:
    """Make a comic its file name matches, with a ComicInfo.xml no parser reads."""
    return make_comic(
        tmp_path / "comics" / "Batman & Robin v2009 001 (2009).cbz",
        formats=(),
        files={"ComicInfo.xml": _BROKEN_CIX},
        series="unused",
        number="1",
    )


@pytest.fixture
def batman_list(tmp_path: Path) -> Path:
    path = tmp_path / "batman.yaml"
    path.write_text(
        "reading_list:\n  name: Batman Reborn\n  entries:\n"
        "    - series: {name: Batman & Robin}\n"
        "      volume: {number: 2009}\n"
        "      issue: {name: '1'}\n"
    )
    return path


def test_match_marks_a_comic_with_an_unreadable_tag_file(
    capsys: pytest.CaptureFixture[str], batman_list: Path, unreadable: Path
) -> None:
    _, out, _ = _run(capsys, "match", str(batman_list), str(unreadable.parent))
    assert f"{unreadable.name} (unreadable ComicInfo.xml)" in _flat(out)


def test_worker_warnings_honour_quiet(
    capfd: pytest.CaptureFixture[str], batman_list: Path, unreadable: Path
) -> None:
    directory = str(unreadable.parent)
    _main("match", str(batman_list), directory)
    loud = capfd.readouterr().err
    _main("-QQ", "match", str(batman_list), directory)
    quiet = capfd.readouterr().err

    # Once: looking for unreadable tag files must not warn of them again.
    assert loud.count("Unable to load") == 1
    assert "Unable to load" not in quiet


# ------------------------------------------------------- write-arcs: plan


def test_a_dry_run_changes_no_byte(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, out, err = _write(capsys, str(reading_list), str(library))

    assert code == 0
    assert digests(library) == before
    assert "cw1.cbz would add 'Civil War' #1" in _flat(out)
    assert "asm532.cbz: found only by a name variant; --variants tags it" in _flat(out)
    assert "Dry run: 1 of 1 matched comic would change; --apply writes them." in err
    assert "1 comic found only by a name variant; --variants tags them." in err
    assert "2 entries matched nothing." in err


def test_a_variant_is_tagged_only_with_variants(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, _ = _write(
        capsys, "--variants", str(reading_list), str(library), apply=True
    )

    assert code == 0
    assert "asm532.cbz added 'Civil War' #3" in _flat(out)
    assert _arcs(library)["asm532.cbz"] == {"Civil War": {"number": 3}}


def test_write_arcs_warns_of_entries_with_no_key(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, library: Path
) -> None:
    keyless = tmp_path / "keyless.yaml"
    keyless.write_text(
        "reading_list:\n  name: Civil War\n  entries:\n"
        "    - series: {name: Civil War}\n      issue: {name: '1'}\n"
    )

    _, _, err = _write(capsys, str(keyless), str(library))

    assert "1 entry matched nothing." in err
    assert "1 entry has no key and matches nothing" in err


def test_a_renumber_of_an_arc_with_no_number(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    make_comic(
        directory / "cw4.cbz",
        series="Civil War",
        number="2",
        start_year=2006,
        arcs={"Civil War": None},
    )

    _, out, _ = _write(capsys, str(reading_list), str(directory))

    assert "would renumber 'Civil War' #2, had no number" in _flat(out)


def test_a_list_name_a_format_cannot_hold_refuses_its_w(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """ComicInfo splits arcs on commas: this one would be written as two."""
    name = "'Avengers, The: Disassembled'"
    listed = _write_list(tmp_path / "list.yaml", name)
    missing = tmp_path / "not-even-read"

    code, _, err = _write(capsys, "-w", "cix", str(listed), str(missing))

    assert code == 2
    assert (
        "-w: ComicInfo.xml cannot hold the arc 'Avengers, The: Disassembled':"
        " it reads it back as other arcs"
    ) in err
    assert "not a directory" not in err


def test_a_format_with_no_arcs_refuses_its_w(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, _, err = _run(
        capsys, "write-arcs", "--apply", "-w", "cbi", str(reading_list), str(library)
    )

    assert code == 2
    assert (
        "ComicBookInfo comment cannot hold the arc 'Civil War': it has no story arcs"
        in err
    )
    assert digests(library) == before


def test_write_arcs_needs_formats(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, _, err = _run(capsys, "write-arcs", str(reading_list), str(library))
    assert code == 2
    assert "-w/--write" in err


def test_an_unknown_format_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, _, err = _write(
        capsys, "-w", "nonsense", str(reading_list), str(library), apply=True
    )

    assert code == 2
    assert "-w nonsense: not a tag format comicbox writes into a comic" in err
    assert digests(library) == before


def test_a_list_without_a_name_names_no_arc(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, library: Path
) -> None:
    nameless = tmp_path / "nameless.yaml"
    nameless.write_text(
        "reading_list:\n  entries:\n"
        "    - series: {name: Civil War, start_year: 2006}\n      issue: {name: '1'}\n"
    )

    code, _, err = _write(capsys, str(nameless), str(library))

    assert code == 1
    assert "the list has no name to tag its arc with" in err


# ---------------------------------------------- write-arcs: what is written


@pytest.mark.parametrize(
    ("formats", "keys", "files"),
    [
        ((_CIX,), "cix", ["ComicInfo.xml"]),
        ((_MI,), "mi", ["MetronInfo.xml"]),
        (
            (JSON, _CIX, _MI),
            "json,cix,mi",
            ["ComicInfo.xml", "MetronInfo.xml", "comicbox.json"],
        ),
    ],
)
def test_a_comic_in_each_format_gets_the_arc(
    capsys: pytest.CaptureFixture[str],
    reading_list: Path,
    tmp_path: Path,
    formats: tuple[str, ...],
    keys: str,
    files: list[str],
) -> None:
    """The arc lands in every format written, and nothing else changes."""
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=formats,
        series="Civil War",
        number="1",
        volume=2006,
        arcs={"Other": 5},
    )
    before = _tags(path)

    code, out, _ = _write(
        capsys, "-w", keys, str(reading_list), str(path.parent), apply=True
    )

    assert code == 0
    assert "cw1.cbz added 'Civil War' #1" in _flat(out)
    assert tag_files(path) == files
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        for name in files:
            assert "Civil War" in archive.read(name).decode()
    after = _tags(path)
    assert after.pop("arcs") == {"Civil War": {"number": 1}, "Other": {"number": 5}}
    before.pop("arcs")
    assert after == before


def test_a_list_name_with_a_comma_is_written_once(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """In a format that holds it, the arc reads back whole: not re-added each run."""
    listed = _write_list(tmp_path / "list.yaml", "'Avengers, The: Disassembled'")
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz", series="Civil War", number="1", start_year=2006
    )

    code, _, _ = _write(capsys, str(listed), str(path.parent), apply=True)
    _, again, _ = _write(capsys, str(listed), str(path.parent), apply=True)

    assert code == 0
    assert _tags(path)["arcs"] == {"Avengers, The: Disassembled": {"number": 1}}
    assert "cw1.cbz: already has 'Avengers, The: Disassembled' #1" in _flat(again)


def test_the_merge_is_additive_whatever_the_config_says(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """Under merge_mode: update the patch's arcs replaced the comic's others."""
    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  write:\n    merge_mode: update\n"
    )
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        series="Civil War",
        number="1",
        start_year=2006,
        arcs={"Other": 5},
    )

    code, _, _ = _write(capsys, str(reading_list), str(path.parent), apply=True)

    assert code == 0
    assert _tags(path)["arcs"] == {"Civil War": {"number": 1}, "Other": {"number": 5}}


def test_the_config_dry_run_wins_and_is_said(
    capsys: pytest.CaptureFixture[str],
    reading_list: Path,
    library: Path,
    tmp_path: Path,
) -> None:
    (tmp_path / "config.yaml").write_text("comicbox:\n  general:\n    dry_run: true\n")
    before = digests(library)

    code, out, err = _write(capsys, str(reading_list), str(library), apply=True)

    assert code == 0
    assert digests(library) == before
    assert "cw1.cbz would add 'Civil War' #1" in _flat(out)
    assert "added" not in _flat(out).replace("would add", "")
    assert "general.dry_run is set in the config, so nothing was written." in err


def test_a_config_that_reads_one_format_loses_nothing_from_another(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """Every tag file is read, so each format is written from all the tags."""
    (tmp_path / "config.yaml").write_text("comicbox:\n  read:\n    formats: [cix]\n")
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=(JSON, _CIX),
        series="Civil War",
        number="1",
        start_year=2006,
        volume=2006,
    )

    _write(capsys, "-w", "json,cix", str(reading_list), str(path.parent), apply=True)

    # ComicInfo has no start year, so only comicbox.json could have kept it.
    written = json.loads(zipfile.ZipFile(path).read("comicbox.json"))
    assert written["comicbox"]["series"]["start_year"] == 2006
    assert written["comicbox"]["arcs"] == {"Civil War": {"number": 1}}


def test_a_write_that_does_not_hold_is_said(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reading_list: Path,
    library: Path,
) -> None:
    """A write comicbox reports done, but that changed nothing, is caught."""
    monkeypatch.setattr(Comicbox, "dump", lambda *_args, **_kwargs: None)

    code, out, _ = _write(capsys, str(reading_list), str(library), apply=True)

    assert code == 1
    assert "cw1.cbz the write did not hold: it reads back without 'Civil War'" in _flat(
        out
    )
    assert "added" not in _flat(out)


def test_apply_with_nothing_to_write_says_so(
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
    untouched = same.read_bytes()

    code, out, err = _write(capsys, str(reading_list), str(directory), apply=True)

    assert code == 0
    assert "cw1.cbz: already has 'Civil War' #1; left alone" in _flat(out)
    assert "Nothing to write among 1 matched comic." in err
    assert same.read_bytes() == untouched


def test_a_comic_with_the_arc_at_another_number_is_renumbered(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    make_comic(
        directory / "cw2.cbz",
        series="Civil War",
        number="2",
        start_year=2006,
        arcs={"Civil War": 9, "Other": 1},
    )
    before = digests(directory)

    _, dry, _ = _write(capsys, str(reading_list), str(directory))
    assert digests(directory) == before
    code, out, _ = _write(capsys, str(reading_list), str(directory), apply=True)

    assert "cw2.cbz would renumber 'Civil War' #2, was #9" in _flat(dry)
    assert code == 0
    assert "cw2.cbz renumbered 'Civil War' #2, was #9" in _flat(out)
    assert _arcs(directory)["cw2.cbz"] == {
        "Civil War": {"number": 2},
        "Other": {"number": 1},
    }


def test_a_comic_with_an_unreadable_tag_file_is_never_written(
    capsys: pytest.CaptureFixture[str], batman_list: Path, unreadable: Path
) -> None:
    """Matched by its file name, its ComicInfo.xml was replaced by one from it."""
    untouched = unreadable.read_bytes()

    code, out, _ = _write(
        capsys, "-w", "cix", str(batman_list), str(unreadable.parent), apply=True
    )

    assert code == 1
    assert "not written: its ComicInfo.xml could not be read" in _flat(out)
    assert unreadable.read_bytes() == untouched


@pytest.mark.parametrize(
    ("comment", "written"),
    [
        # Free text is not a tag file: comicbox's usual write replaces it.
        ("Scanned by a friend", True),
        # A ComicBookInfo comment that does not parse is one.
        ('{"ComicBookInfo/1.0": {"series": "Civil War",', False),
    ],
)
def test_an_archive_comment_is_unreadable_only_when_it_is_json(
    capsys: pytest.CaptureFixture[str],
    reading_list: Path,
    tmp_path: Path,
    comment: str,
    written: bool,
) -> None:
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        comment=comment,
        series="Civil War",
        number="1",
        start_year=2006,
    )

    code, out, _ = _write(capsys, str(reading_list), str(path.parent), apply=True)

    assert (code == 0) is written
    assert ("added 'Civil War' #1" in _flat(out)) is written
    assert ("its archive comment could not be read" in _flat(out)) is not written


@pytest.mark.parametrize(
    "source", [CBI_CBR_SOURCE_PATH, CIX_CBT_SOURCE_PATH, CB7_SOURCE_PATH]
)
def test_an_archive_comicbox_cannot_write_is_converted(
    capsys: pytest.CaptureFixture[str], captain_list: Path, tmp_path: Path, source: Path
) -> None:
    """As with any comicbox write, and the CBZ is the one read back."""
    comics = tmp_path / "comics"
    comics.mkdir()
    copy = comics / source.name
    shutil.copy(source, copy)
    untouched = copy.read_bytes()

    code, out, _ = _write(
        capsys, "-w", "cix", str(captain_list), str(comics), apply=True
    )

    converted = copy.with_suffix(".cbz")
    assert code == 0
    assert "'Captain Arc' #1" in _flat(out)
    assert _flat(out).endswith(f" as {converted.name}")
    assert copy.read_bytes() == untouched
    assert _tags(converted)["arcs"]["Captain Arc"] == {"number": 1}


@pytest.fixture
def captain_list(tmp_path: Path) -> Path:
    path = tmp_path / "captain.yaml"
    path.write_text(
        "reading_list:\n  name: Captain Arc\n  entries:\n"
        "    - series: {name: Captain Science}\n"
        "      volume: {number: 1950}\n"
        "      issue: {name: '1'}\n"
    )
    return path


@pytest.mark.parametrize("source", [PDF_SOURCE_PATH, CIX_PDF_SOURCE_PATH])
def test_a_pdf_is_written_in_place(
    capsys: pytest.CaptureFixture[str], captain_list: Path, tmp_path: Path, source: Path
) -> None:
    """Matched by its file name, a PDF gets its ComicInfo there."""
    comics = tmp_path / "comics"
    comics.mkdir()
    pdf = comics / "Captain Science v1950 #001.pdf"
    shutil.copy(source, pdf)

    code, out, _ = _write(
        capsys, "-w", "cix", str(captain_list), str(comics), apply=True
    )

    assert code == 0
    assert f"{pdf} added 'Captain Arc' #1" in _flat(out)
    assert sorted(path.name for path in comics.iterdir()) == [pdf.name]
    assert _tags(pdf)["arcs"] == {"Captain Arc": {"number": 1}}


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_one_file_is_written_once(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path, link: str
) -> None:
    """lib/link0.cbz and the cw1.cbz it names were both written at once."""
    target = library / "cw1.cbz"
    other = library / "lib" / "link0.cbz"
    other.parent.mkdir()
    if link == "symlink":
        other.symlink_to(target)
    else:
        other.hardlink_to(target)

    code, out, _ = _write(capsys, str(reading_list), str(library), apply=True)

    flat = _flat(out)
    assert code == 0
    assert flat.count("added 'Civil War' #1") == 1
    assert f"{other}: same file as {target}" in flat
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
    assert _tags(target)["arcs"] == {"Civil War": {"number": 1}}


def test_a_read_only_comic_fails_and_the_rest_are_written(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    comics = tmp_path / "comics"
    locked = make_comic(
        comics / "cw1.cbz", series="Civil War", number="1", start_year=2006
    )
    make_comic(comics / "cw2.cbz", series="Civil War", number="2", start_year=2006)
    locked.chmod(0o444)
    untouched = locked.read_bytes()
    try:
        code, out, err = _write(capsys, str(reading_list), str(comics), apply=True)
    finally:
        locked.chmod(0o644)

    assert code == 1
    assert "cw1.cbz: Permission denied" in err
    assert locked.read_bytes() == untouched
    assert "cw2.cbz added 'Civil War' #2" in _flat(out)
    assert "1 of 2 matched comics written." in err


# ---------------------------------------------------------------- Ctrl-C

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
            library / f"saga{number:02}.cbz",
            series="Saga",
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


# ----------------------------------------------------------- write-arcs: Ctrl-C


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
    import comicbox.write

    numbers = [str(number) for number in range(1, 21)]
    listed = tmp_path / "list.yaml"
    listed.write_text(
        "reading_list:\n  name: Civil War\n  entries:\n"
        + "".join(
            f"    - series: {{name: Civil War, start_year: 2006}}\n"
            f"      issue: {{name: '{number}'}}\n"
            for number in numbers
        )
    )
    comics = tmp_path / "comics"
    for number in numbers:
        make_comic(
            comics / f"cw{number:>02}.cbz",
            series="Civil War",
            number=number,
            start_year=2006,
        )
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

    code, out, err = _write(capsys, str(listed), str(comics), apply=True)

    flat = _flat(out)
    assert code == 130
    assert f"{pressed[0]} added 'Civil War'" in flat
    assert "not written: cancelled" in flat
    assert "Stopping after the writes under way." in err
    assert err.endswith("Cancelled.")
    for path in comics.iterdir():
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
        written = f"{path} added" in flat
        assert ("Civil War" in (_tags(path).get("arcs") or {})) is written
