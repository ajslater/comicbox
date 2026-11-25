"""
``comicbox rl write-arcs``: conversions, links, and failed writes.

Every comic is generated under tmp_path, or copied there from
tests/files: write-arcs changes comics, so no test points it at anything
else. Every write goes through the real ``bulk_write``.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from typing import TYPE_CHECKING

import pytest

from tests.const import (
    CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
)
from tests.util.comics import JSON, digests, make_comic
from tests.util.readinglist_cli import (
    CIX,
    MI,
    flat,
    read_tags,
    rl_write,
    write_list,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


@pytest.fixture
def cbr(tmp_path: Path) -> Path:
    comics = tmp_path / "comics"
    comics.mkdir()
    copy = comics / CBI_CBR_SOURCE_PATH.name
    shutil.copy(CBI_CBR_SOURCE_PATH, copy)
    return copy


def test_the_dry_run_shows_a_conversion(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    before = digests(cbr.parent)

    _, out, _ = rl_write(capsys, "-w", "cix", str(captain_list), str(cbr.parent))
    _, deleting, _ = rl_write(
        capsys, "-w", "cix", "--delete-orig", str(captain_list), str(cbr.parent)
    )

    cbz = cbr.with_suffix(".cbz").name
    assert f"would convert to {cbz} and keep the CBR" in flat(out)
    assert f"would convert to {cbz} and delete the CBR" in flat(deleting)
    assert digests(cbr.parent) == before


def test_a_conversion_onto_a_file_already_there_is_refused_up_front(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    """The 5.2.0 refusal, named by the dry run, not only by the write."""
    occupied = cbr.with_suffix(".cbz")
    occupied.write_bytes(b"someone else's comic")
    before = digests(cbr.parent)

    _, dry, _ = rl_write(capsys, "-w", "cix", str(captain_list), str(cbr.parent))
    code, out, _ = rl_write(
        capsys, "-w", "cix", str(captain_list), str(cbr.parent), apply=True
    )

    reason = f"{cbr} not written: {occupied.name} already exists"
    assert reason in flat(dry)
    assert reason in flat(out)
    assert code == 1
    assert digests(cbr.parent) == before


def test_two_conversions_onto_one_cbz_are_shown_by_the_dry_run(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    cbt = cbr.with_suffix(".cbt")
    shutil.copy(CIX_CBT_SOURCE_PATH, cbt)

    _, dry, _ = rl_write(capsys, "-w", "cix", str(captain_list), str(cbr.parent))

    first, second = sorted((cbr, cbt))
    assert f"{first.name} would " in flat(dry)
    assert (
        f"{second} not written: {cbr.with_suffix('.cbz').name} is also the"
        f" destination of {first}"
    ) in flat(dry)


def test_delete_orig_removes_the_original_after_a_good_conversion(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    code, out, _ = rl_write(
        capsys,
        "-w",
        "cix",
        "--delete-orig",
        str(captain_list),
        str(cbr.parent),
        apply=True,
    )

    cbz = cbr.with_suffix(".cbz")
    assert code == 0
    assert f"as {cbz.name}; deleted the CBR" in flat(out)
    assert not cbr.exists()
    assert read_tags(cbz)["arcs"] == {"Captain Arc": {"number": 1}}


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

    code, out, _ = rl_write(capsys, str(reading_list), str(library), apply=True)

    said = flat(out)
    assert code == 0
    assert said.count("added 'Crimson Tide' #1") == 1
    assert f"{other}: same file as {target}" in said
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
    assert read_tags(target)["arcs"] == {"Crimson Tide": {"number": 1}}


def test_a_conversion_through_a_link_converts_the_file_it_names(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    """It converted the link, said it deleted the CBR, and left the CBR untagged."""
    link = cbr.parent / "A-link.cbr"
    link.symlink_to(cbr)
    args = ("-w", "cix", "--delete-orig", str(captain_list), str(cbr.parent))

    _, dry, _ = rl_write(capsys, *args)
    code, out, _ = rl_write(capsys, *args, apply=True)
    again, rerun, _ = rl_write(capsys, *args, apply=True)

    cbz = cbr.with_suffix(".cbz")
    assert f"{link}: same file as {cbr}; would be removed with it" in flat(dry)
    assert code == 0
    assert f"{cbr} added 'Captain Arc' #1 as {cbz.name}; deleted the CBR" in flat(out)
    # B8: every path naming the deleted original goes with it.
    assert f"{link}: same file as {cbr}; removed with it" in flat(out)
    assert f"{cbr}: same file" not in flat(out)
    assert sorted(cbr.parent.iterdir()) == [cbz]
    assert read_tags(cbz)["arcs"] == {"Captain Arc": {"number": 1}}
    assert again == 0
    assert "already has 'Captain Arc' #1" in flat(rerun)


def test_delete_orig_removes_a_hard_link_to_the_converted_original(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    """B8: the second name kept the old CBR, and a rerun converted it again."""
    other = cbr.parent / "Z-other.cbr"
    other.hardlink_to(cbr)
    args = ("-w", "cix", "--delete-orig", str(captain_list), str(cbr.parent))

    code, out, _ = rl_write(capsys, *args, apply=True)
    again, _, _ = rl_write(capsys, *args, apply=True)

    cbz = cbr.with_suffix(".cbz")
    assert code == 0
    assert f"{other}: same file as {cbr}; removed with it" in flat(out)
    assert again == 0
    assert sorted(cbr.parent.iterdir()) == [cbz]


def test_a_link_to_a_comic_elsewhere_writes_that_comic(
    capsys: pytest.CaptureFixture[str], captain_list: Path, cbr: Path
) -> None:
    library = cbr.parent.parent / "library"
    library.mkdir()
    link = library / "Captain.cbr"
    link.symlink_to(cbr)

    code, out, _ = rl_write(
        capsys, "-w", "cix", str(captain_list), str(library), apply=True
    )

    cbz = cbr.with_suffix(".cbz")
    assert code == 0
    assert f"{cbr} added 'Captain Arc' #1 as {cbz.name}" in flat(out)
    assert f"{link}: same file as {cbr}" in flat(out)
    assert list(library.iterdir()) == [link]
    assert read_tags(cbz)["arcs"] == {"Captain Arc": {"number": 1}}


def test_keep_does_not_write_a_kept_format_that_splits_the_arc(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A kept ComicInfo got two bogus arcs, and the next write spread them."""
    reading_list = write_list(tmp_path / "avx.yaml", name="'Ardent, The: Disassembled'")
    comics = tmp_path / "comics"
    split = make_comic(
        comics / "cw1.cbz",
        formats=(CIX, JSON),
        series="Crimson Tide",
        number="1",
        start_year=2006,
    )
    held = make_comic(
        comics / "cw2.cbz",
        formats=(MI,),
        series="Crimson Tide",
        number="2",
        volume=2006,
    )
    untouched = split.read_bytes()

    named, _, named_err = rl_write(capsys, "-w", "cix", str(reading_list), str(comics))
    code, out, _ = rl_write(
        capsys, "-w", "keep", str(reading_list), str(comics), apply=True
    )

    assert named == 2
    assert "ComicInfo.xml cannot hold the arc" in named_err
    assert code == 1
    assert (
        "cw1.cbz not written: its ComicInfo.xml would read the arc back as other arcs"
    ) in flat(out)
    assert split.read_bytes() == untouched
    assert read_tags(held)["arcs"] == {"Ardent, The: Disassembled": {"number": 2}}


def test_a_write_without_keep_leaves_a_free_text_comment(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """B1: -w without keep cleared a scanner's note, and said so."""
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        comment="Scanned by a friend",
        series="Crimson Tide",
        number="1",
        start_year=2006,
    )

    _, dry, dry_err = rl_write(capsys, str(reading_list), str(path.parent))
    code, out, _ = rl_write(capsys, str(reading_list), str(path.parent), apply=True)

    assert "cw1.cbz would add 'Crimson Tide' #1" in flat(dry)
    assert "comment" not in flat(dry) + dry_err
    assert "Add keep" not in dry_err
    assert code == 0
    assert "clear" not in out
    with zipfile.ZipFile(path) as archive:
        assert archive.comment == b"Scanned by a friend"


def test_the_summary_counts_comics_that_lose_a_tag_file(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """It read "3 comics would lose a tag files"."""
    comics = tmp_path / "comics"
    for number in ("1", "2", "7"):
        make_comic(
            comics / f"cw{number}.cbz",
            formats=(MI,),
            series="Crimson Tide",
            number=number,
            start_year=2006,
        )

    _, _, err = rl_write(capsys, "-w", "cix", str(reading_list), str(comics))

    assert "3 comics would lose a tag file." in err


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes any file")
def test_a_read_only_comic_fails_and_the_rest_are_written(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    comics = tmp_path / "comics"
    locked = make_comic(
        comics / "cw1.cbz", series="Crimson Tide", number="1", start_year=2006
    )
    make_comic(comics / "cw2.cbz", series="Crimson Tide", number="2", start_year=2006)
    locked.chmod(0o444)
    untouched = locked.read_bytes()
    try:
        code, out, err = rl_write(capsys, str(reading_list), str(comics), apply=True)
    finally:
        locked.chmod(0o644)

    assert code == 1
    assert "cw1.cbz: Permission denied" in err
    assert locked.read_bytes() == untouched
    assert "cw2.cbz added 'Crimson Tide' #2" in flat(out)
    assert "1 of 2 matched comics written." in err
