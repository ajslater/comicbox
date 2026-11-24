"""
``comicbox rl write-arcs``: the tag files -w removes, and keep.

Every comic is generated under tmp_path, or copied there from
tests/files: write-arcs changes comics, so no test points it at anything
else. Every write goes through the real ``bulk_write``.
"""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING, Any

import pytest

from tests.util.comics import JSON, make_comic, tag_files
from tests.util.readinglist_cli import (
    CIX,
    MI,
    flat,
    read_tags,
    rl_write,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("restore_cli_state")


def test_each_comic_names_the_tag_files_w_removes(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """A MetronInfo comic under -w cix loses MetronInfo.xml, and is told so."""
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=(MI,),
        series="Civil War",
        number="1",
        start_year=2006,
    )

    _, dry, dry_err = rl_write(capsys, "-w", "cix", str(reading_list), str(path.parent))
    code, out, err = rl_write(
        capsys, "-w", "cix", str(reading_list), str(path.parent), apply=True
    )

    assert "cw1.cbz would add 'Civil War' #1; would remove MetronInfo.xml" in flat(dry)
    assert "1 comic would lose a tag file." in dry_err
    assert dry_err.endswith("Add keep to -w to keep them: -w cix,keep.")
    assert code == 0
    assert "cw1.cbz added 'Civil War' #1; removed MetronInfo.xml" in flat(out)
    assert "1 comic lost a tag file." in err
    assert "Add keep" not in err
    assert tag_files(path) == ["ComicInfo.xml"]


def _one_comic_per_format(comics: Path) -> list[Path]:
    """Make Civil War #1, #2 and #7 in comicbox.json, MetronInfo, and both XMLs."""
    return [
        make_comic(comics / "cw1.cbz", series="Civil War", number="1", start_year=2006),
        make_comic(
            comics / "cw2.cbz",
            formats=(MI,),
            series="Civil War",
            number="2",
            start_year=2006,
            arcs={"Other": 3},
        ),
        make_comic(
            comics / "cw7.cbz",
            formats=(CIX, MI),
            series="Civil War",
            number="7",
            start_year=2006,
            volume=2006,
        ),
    ]


def _what_the_write_leaves(path: Path) -> tuple[set[str], dict[str, Any]]:
    """Get a comic's tag files and tags, but ComicInfo.xml and the Civil War arc."""
    tags = read_tags(path)
    others = {
        name: arc
        for name, arc in (tags.pop("arcs", None) or {}).items()
        if name != "Civil War"
    }
    files = set(tag_files(path)) - {"ComicInfo.xml"}
    return files, ({**tags, "arcs": others} if others else tags)


def test_the_suggested_w_loses_nothing(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """The dry run's -w, with keep, keeps every tag file of every comic."""
    comics = tmp_path / "comics"
    paths = _one_comic_per_format(comics)
    before = {path: _what_the_write_leaves(path) for path in paths}

    _, _, dry_err = rl_write(capsys, "-w", "cix", str(reading_list), str(comics))
    suggested = dry_err.rsplit("-w ", 1)[1].removesuffix(".")
    code, out, err = rl_write(
        capsys, "-w", suggested, str(reading_list), str(comics), apply=True
    )

    assert suggested == "cix,keep"
    assert code == 0
    assert "remove" not in out
    assert "lost a tag file" not in err
    for path in paths:
        # ComicInfo and the arc are added, and nothing the comic had is gone.
        assert "ComicInfo.xml" in tag_files(path)
        assert "Civil War" in read_tags(path)["arcs"]
        assert _what_the_write_leaves(path) == before[path]


def test_keep_keeps_a_format_w_cannot_name(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    """ComicBookInfo has no arcs, so -w refuses it, but keep keeps the comment."""
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=(JSON, "COMIC_BOOK_INFO"),
        series="Civil War",
        number="1",
        start_year=2006,
    )

    _, dry, err = rl_write(capsys, str(reading_list), str(path.parent))
    code, out, _ = rl_write(
        capsys, "-w", "json,keep", str(reading_list), str(path.parent), apply=True
    )

    assert "would remove ComicBookInfo comment" in flat(dry)
    assert err.endswith("Add keep to -w to keep them: -w json,keep.")
    assert code == 0
    assert "remove" not in out
    with zipfile.ZipFile(path) as archive:
        assert json.loads(archive.comment)["ComicBookInfo/1.0"]["series"] == (
            "Civil War"
        )
    assert read_tags(path)["arcs"] == {"Civil War": {"number": 1}}


def test_w_keep_writes_each_comic_in_its_own_formats(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    comics = tmp_path / "comics"
    metron = make_comic(
        comics / "cw1.cbz",
        formats=(MI,),
        series="Civil War",
        number="1",
        start_year=2006,
    )
    both = make_comic(
        comics / "cw2.cbz",
        formats=(CIX, MI),
        series="Civil War",
        number="2",
        start_year=2006,
        volume=2006,
    )

    _, dry, _ = rl_write(capsys, "-w", "keep", str(reading_list), str(comics))
    code, out, _ = rl_write(
        capsys, "-w", "keep", str(reading_list), str(comics), apply=True
    )

    assert "remove" not in dry
    assert code == 0
    assert "remove" not in out
    assert tag_files(metron) == ["MetronInfo.xml"]
    assert tag_files(both) == ["ComicInfo.xml", "MetronInfo.xml"]
    assert read_tags(metron)["arcs"] == {"Civil War": {"number": 1}}
    assert read_tags(both)["arcs"] == {"Civil War": {"number": 2}}


def test_w_keep_does_not_write_a_comic_with_no_format_that_holds_the_arc(
    capsys: pytest.CaptureFixture[str], reading_list: Path, tmp_path: Path
) -> None:
    path = make_comic(
        tmp_path / "comics" / "cw1.cbz",
        formats=("COMIC_BOOK_INFO",),
        series="Civil War",
        number="1",
        volume=2006,
    )
    untouched = path.read_bytes()

    code, out, _ = rl_write(
        capsys, "-w", "keep", str(reading_list), str(path.parent), apply=True
    )

    assert code == 1
    assert (
        "cw1.cbz not written: it has ComicBookInfo comment, none of which can"
        " hold the arc"
    ) in flat(out)
    assert path.read_bytes() == untouched


def test_w_keep_alone_is_not_refused_for_naming_no_format(
    capsys: pytest.CaptureFixture[str], reading_list: Path, library: Path
) -> None:
    code, _, err = rl_write(capsys, "-w", "keep", str(reading_list), str(library))
    assert code == 0
    assert "-w names no format" not in err
