"""
``comicbox rl write-arcs``: its plan, and what it writes.

Every comic is generated under tmp_path, or copied there from
tests/files: write-arcs changes comics, so no test points it at anything
else. Every write goes through the real ``bulk_write``.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from tests.const import (
    CB7_SOURCE_PATH,
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_PDF_SOURCE_PATH,
    PDF_SOURCE_PATH,
)
from tests.util.comics import JSON, digests, make_comic, tag_files
from tests.util.readinglist_cli import (
    CIX,
    MI,
    flat,
    read_arcs,
    read_tags,
    rl_run,
    rl_write,
    write_list,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


# ------------------------------------------------------------------ plan


def test_a_dry_run_changes_no_byte(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, out, err = rl_write(capsys, str(reading_list), str(library))

    assert code == 0
    assert digests(library) == before
    assert "cw1.cbz would add 'Crimson Tide' #1" in flat(out)
    assert "asm532.cbz: found only by a name variant; --variants tags it" in flat(out)
    assert "Dry run: 1 of 1 matched comic would change; --apply writes them." in err
    assert "1 comic found only by a name variant; --variants tags them." in err
    assert "2 entries matched nothing." in err


def test_a_variant_is_tagged_only_with_variants(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, out, _ = rl_write(
        capsys, "--variants", str(reading_list), str(library), apply=True
    )

    assert code == 0
    assert "asm532.cbz added 'Crimson Tide' #3" in flat(out)
    assert read_arcs(library)["asm532.cbz"] == {"Crimson Tide": {"number": 3}}


def test_write_arcs_warns_of_entries_with_no_key(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, library: Path
) -> None:
    keyless = tmp_path / "keyless.yaml"
    keyless.write_text(
        "reading_list:\n  name: Crimson Tide\n  entries:\n"
        "    - series: {name: Crimson Tide}\n      issue: {name: '1'}\n"
    )

    _, _, err = rl_write(capsys, str(keyless), str(library))

    assert "1 entry matched nothing." in err
    assert "1 entry has no key and matches nothing" in err


def test_a_renumber_of_an_arc_with_no_number(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    make_comic(
        directory / "cw4.cbz",
        series="Crimson Tide",
        number="2",
        start_year=2006,
        arcs={"Crimson Tide": None},
    )

    _, out, _ = rl_write(capsys, str(reading_list), str(directory))

    assert "would renumber 'Crimson Tide' #2, had no number" in flat(out)


def test_a_list_name_a_format_cannot_hold_refuses_its_w(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """ComicInfo splits arcs on commas: this one would be written as two."""
    name = "'Ardent, The: Disassembled'"
    listed = write_list(tmp_path / "list.yaml", name)
    missing = tmp_path / "not-even-read"

    code, _, err = rl_write(capsys, "-w", "cix", str(listed), str(missing))

    assert code == 2
    assert (
        "-w: ComicInfo.xml cannot hold the arc 'Ardent, The: Disassembled':"
        " it reads it back as other arcs"
    ) in err
    assert "not a directory" not in err


def test_a_format_with_no_arcs_refuses_its_w(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, _, err = rl_run(
        capsys, "write-arcs", "--apply", "-w", "cbi", str(reading_list), str(library)
    )

    assert code == 2
    assert (
        "ComicBookInfo comment cannot hold the arc 'Crimson Tide': it has no story arcs"
        in err
    )
    assert digests(library) == before


def test_write_arcs_needs_formats(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, _, err = rl_run(capsys, "write-arcs", str(reading_list), str(library))
    assert code == 2
    assert "-w/--write" in err


def test_an_unknown_format_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    before = digests(library)

    code, _, err = rl_write(
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
        "    - series: {name: Crimson Tide, start_year: 2006}\n      issue: {name: '1'}\n"
    )

    code, _, err = rl_write(capsys, str(nameless), str(library))

    assert code == 1
    assert "the list has no name to tag its arc with" in err


# ------------------------------------------------------- what is written


@pytest.mark.parametrize(
    ("formats", "keys", "files"),
    [
        ((CIX,), "cix", ["ComicInfo.xml"]),
        ((MI,), "mi", ["MetronInfo.xml"]),
        (
            (JSON, CIX, MI),
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
        series="Crimson Tide",
        number="1",
        volume=2006,
        arcs={"Other": 5},
    )
    before = read_tags(path)

    code, out, _ = rl_write(
        capsys, "-w", keys, str(reading_list), str(path.parent), apply=True
    )

    assert code == 0
    assert "cw1.cbz added 'Crimson Tide' #1" in flat(out)
    assert tag_files(path) == files
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        for name in files:
            assert "Crimson Tide" in archive.read(name).decode()
    after = read_tags(path)
    assert after.pop("arcs") == {"Crimson Tide": {"number": 1}, "Other": {"number": 5}}
    before.pop("arcs")
    assert after == before


def test_a_list_name_with_a_comma_is_written_once(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """In a format that holds it, the arc reads back whole: not re-added each run."""
    listed = write_list(tmp_path / "list.yaml", "'Ardent, The: Disassembled'")
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        series="Crimson Tide",
        number="1",
        start_year=2006,
    )

    code, _, _ = rl_write(capsys, str(listed), str(path.parent), apply=True)
    _, again, _ = rl_write(capsys, str(listed), str(path.parent), apply=True)

    assert code == 0
    assert read_tags(path)["arcs"] == {"Ardent, The: Disassembled": {"number": 1}}
    assert "cw1.cbz: already has 'Ardent, The: Disassembled' #1" in flat(again)


def test_the_merge_is_additive_whatever_the_config_says(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """Under merge_mode: update the patch's arcs replaced the comic's others."""
    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  write:\n    merge_mode: update\n"
    )
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        series="Crimson Tide",
        number="1",
        start_year=2006,
        arcs={"Other": 5},
    )

    code, _, _ = rl_write(capsys, str(reading_list), str(path.parent), apply=True)

    assert code == 0
    assert read_tags(path)["arcs"] == {
        "Crimson Tide": {"number": 1},
        "Other": {"number": 5},
    }


def test_the_config_dry_run_wins_and_is_said(
    capsys: pytest.CaptureFixture[str],
    reading_list: Path,
    library: Path,
    tmp_path: Path,
) -> None:
    (tmp_path / "config.yaml").write_text("comicbox:\n  general:\n    dry_run: true\n")
    before = digests(library)

    code, out, err = rl_write(capsys, str(reading_list), str(library), apply=True)

    assert code == 0
    assert digests(library) == before
    assert "cw1.cbz would add 'Crimson Tide' #1" in flat(out)
    assert "added" not in flat(out).replace("would add", "")
    assert "general.dry_run is set in the config, so nothing was written." in err


def test_a_config_that_reads_one_format_loses_nothing_from_another(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """Every tag file is read, so each format is written from all the tags."""
    (tmp_path / "config.yaml").write_text("comicbox:\n  read:\n    formats: [cix]\n")
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=(JSON, CIX),
        series="Crimson Tide",
        number="1",
        start_year=2006,
        volume=2006,
    )

    rl_write(capsys, "-w", "json,cix", str(reading_list), str(path.parent), apply=True)

    # ComicInfo has no start year, so only comicbox.json could have kept it.
    written = json.loads(zipfile.ZipFile(path).read("comicbox.json"))
    assert written["comicbox"]["series"]["start_year"] == 2006
    assert written["comicbox"]["arcs"] == {"Crimson Tide": {"number": 1}}


def test_a_write_that_does_not_hold_is_said(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reading_list: Path,
    library: Path,
) -> None:
    """A write comicbox reports done, but that changed nothing, is caught."""
    monkeypatch.setattr(Comicbox, "dump", lambda *_args, **_kwargs: None)

    code, out, _ = rl_write(capsys, str(reading_list), str(library), apply=True)

    assert code == 1
    assert (
        "cw1.cbz the write did not hold: it reads back without 'Crimson Tide'"
        in flat(out)
    )
    assert "added" not in flat(out)


def test_apply_with_nothing_to_write_says_so(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    same = make_comic(
        directory / "cw1.cbz",
        series="Crimson Tide",
        number="1",
        start_year=2006,
        arcs={"Crimson Tide": 1},
    )
    untouched = same.read_bytes()

    code, out, err = rl_write(capsys, str(reading_list), str(directory), apply=True)

    assert code == 0
    assert "cw1.cbz: already has 'Crimson Tide' #1; left alone" in flat(out)
    assert "Nothing to write among 1 matched comic." in err
    assert same.read_bytes() == untouched


def test_a_comic_with_the_arc_at_another_number_is_renumbered(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "tagged"
    make_comic(
        directory / "cw2.cbz",
        series="Crimson Tide",
        number="2",
        start_year=2006,
        arcs={"Crimson Tide": 9, "Other": 1},
    )
    before = digests(directory)

    _, dry, _ = rl_write(capsys, str(reading_list), str(directory))
    assert digests(directory) == before
    code, out, _ = rl_write(capsys, str(reading_list), str(directory), apply=True)

    assert "cw2.cbz would renumber 'Crimson Tide' #2, was #9" in flat(dry)
    assert code == 0
    assert "cw2.cbz renumbered 'Crimson Tide' #2, was #9" in flat(out)
    assert read_arcs(directory)["cw2.cbz"] == {
        "Crimson Tide": {"number": 2},
        "Other": {"number": 1},
    }


def test_a_comic_with_an_unreadable_tag_file_is_never_written(
    capsys: pytest.CaptureFixture[str], bladehawk_list: Path, unreadable: Path
) -> None:
    """Matched by its file name, its ComicInfo.xml was replaced by one from it."""
    untouched = unreadable.read_bytes()

    code, out, _ = rl_write(
        capsys, "-w", "cix", str(bladehawk_list), str(unreadable.parent), apply=True
    )

    assert code == 1
    assert "not written: its ComicInfo.xml could not be read" in flat(out)
    assert unreadable.read_bytes() == untouched


@pytest.mark.parametrize(
    "comment",
    [
        "Scanned by a friend",
        # Not JSON, so not ComicBookInfo, whatever it starts with.
        '{"ComicBookInfo/1.0": {"series": "Crimson Tide",',
    ],
)
def test_an_archive_comment_that_is_not_comic_book_info_is_free_text(
    capsys: pytest.CaptureFixture[str],
    reading_list: Path,
    tmp_path: Path,
    comment: str,
) -> None:
    """Free text is not a tag file: comicbox's usual write replaces it."""
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        comment=comment,
        series="Crimson Tide",
        number="1",
        start_year=2006,
    )

    code, out, _ = rl_write(capsys, str(reading_list), str(path.parent), apply=True)

    assert code == 0
    assert "added 'Crimson Tide' #1" in flat(out)
    assert "could not be read" not in flat(out)


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

    code, out, _ = rl_write(
        capsys, "-w", "cix", str(captain_list), str(comics), apply=True
    )

    converted = copy.with_suffix(".cbz")
    assert code == 0
    assert "'Captain Arc' #1" in flat(out)
    assert f" as {converted.name}" in flat(out)
    assert copy.read_bytes() == untouched
    assert read_tags(converted)["arcs"]["Captain Arc"] == {"number": 1}


@pytest.mark.parametrize("source", [PDF_SOURCE_PATH, CIX_PDF_SOURCE_PATH])
def test_a_pdf_is_written_in_place(
    capsys: pytest.CaptureFixture[str], captain_list: Path, tmp_path: Path, source: Path
) -> None:
    """Matched by its file name, a PDF gets its ComicInfo there."""
    comics = tmp_path / "comics"
    comics.mkdir()
    pdf = comics / "Captain Science v1950 #001.pdf"
    shutil.copy(source, pdf)

    code, out, _ = rl_write(
        capsys, "-w", "cix", str(captain_list), str(comics), apply=True
    )

    assert code == 0
    assert f"{pdf} added 'Captain Arc' #1" in flat(out)
    # The PDF metadata stays, so it is not named as removed.
    assert "remove" not in out
    assert sorted(path.name for path in comics.iterdir()) == [pdf.name]
    assert read_tags(pdf)["arcs"] == {"Captain Arc": {"number": 1}}
