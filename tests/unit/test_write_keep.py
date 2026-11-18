"""
``-w keep``: a write that removes no tag format the comic carries.

Through the real write path, on generated archives or copies of
tests/files: ``write_metadata``, ``bulk_write`` and the main CLI.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import zipfile
from argparse import Namespace
from typing import TYPE_CHECKING, Any

import pytest

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.exceptions import ArchiveWriteError
from comicbox.write import (
    BulkWriteItem,
    WriteValidationError,
    bulk_write,
    write_metadata,
)
from tests.const import CBI_CBR_SOURCE_PATH, CIX_CBT_SOURCE_PATH, CIX_PDF_SOURCE_PATH
from tests.util.comics import JSON, make_comic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_CIX = "COMIC_INFO"
_MI = "METRON_INFO"
_ALL = (_CIX, _MI, "COMET", JSON, "COMICBOX_YAML", "COMIC_BOOK_INFO")
_PATCH = {"summary": "Kept"}
# What every write adds, keep or not: the patch, and comicbox's stamp.
_WRITE_ADDS = ("summary", "notes", "tagger", "updated_at")
_TAGS: dict[str, Any] = {"series": "Civil War", "number": "1", "volume": 2006}


def _tag_files(path: Path) -> tuple[list[str], bytes]:
    """List a CBZ's tag files, by lower-case name, and its comment."""
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name.lower()
            for name in archive.namelist()
            if not name.lower().endswith((".jpg", ".png", ".webp"))
        )
        return names, archive.comment


def _member(names: Iterable[str], filename: str) -> str:
    """Find the one archive member, at any depth, with this file name."""
    (name,) = (name for name in names if name.lower().endswith(filename.lower()))
    return name


def _tags(path: Path, config: Any = None) -> dict[str, Any]:
    with Comicbox(path, config=config) as box:
        return dict(box.to_dict()["comicbox"])


def _unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Compare tags apart from what the write added; check it added the patch."""
    assert after.get("summary") == "Kept"
    for key in _WRITE_ADDS:
        before.pop(key, None)
        after.pop(key, None)
    return after == before


def _config(**dests: Any) -> Any:
    return get_config(Namespace(comicbox=Namespace(**dests)))


@pytest.mark.parametrize(
    "formats",
    [(_CIX,), (_MI,), _ALL],
    ids=["comicinfo", "metroninfo", "every-format"],
)
def test_keep_writes_back_what_the_comic_has(
    tmp_path: Path, formats: tuple[str, ...]
) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=formats, **_TAGS)
    files, comment = _tag_files(path)
    before = _tags(path)

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert result.written, result.error
    after_files, after_comment = _tag_files(path)
    assert after_files == files
    assert bool(after_comment) == bool(comment)
    assert _unchanged(before, _tags(path))
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None


def test_keep_keeps_a_comicbookinfo_comment_a_comment(tmp_path: Path) -> None:
    """-w cbi writes a comic-book-info.json; keep writes it back where it was."""
    path = make_comic(tmp_path / "cw1.cbz", formats=(JSON, "COMIC_BOOK_INFO"), **_TAGS)

    write_metadata(path, _PATCH, formats=["keep"])

    files, comment = _tag_files(path)
    assert files == ["comicbox.json"]
    assert json.loads(comment)["ComicBookInfo/1.0"]["comments"] == "Kept"


def test_keep_leaves_a_free_text_comment(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", comment="Scanned by a friend", **_TAGS)

    write_metadata(path, _PATCH, formats=["keep"])

    assert _tag_files(path) == (["comicbox.json"], b"Scanned by a friend")


def test_a_write_without_keep_leaves_a_free_text_comment(tmp_path: Path) -> None:
    """B1: -w cix emptied a scanner's note, which is no tag format."""
    path = make_comic(tmp_path / "cw1.cbz", comment="Scanned by a friend", **_TAGS)

    write_metadata(path, _PATCH, formats=[_CIX])

    assert _tag_files(path) == (["comicinfo.xml"], b"Scanned by a friend")


def test_a_write_without_keep_removes_a_comicbookinfo_comment(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(JSON, "COMIC_BOOK_INFO"), **_TAGS)

    write_metadata(path, _PATCH, formats=[_CIX])

    assert _tag_files(path) == (["comicinfo.xml"], b"")


def test_a_comicbookinfo_write_leaves_a_free_text_comment(tmp_path: Path) -> None:
    """-w cbi writes a comic-book-info.json, so the note has nothing to make way for."""
    path = make_comic(tmp_path / "cw1.cbz", comment="Scanned by a friend", **_TAGS)

    write_metadata(path, _PATCH, formats=["COMIC_BOOK_INFO"])

    assert _tag_files(path) == (["comic-book-info.json"], b"Scanned by a friend")


def test_delete_all_tags_still_clears_a_free_text_comment(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", comment="Scanned by a friend", **_TAGS)
    config = get_config(
        Namespace(comicbox=Namespace(write=Namespace(delete_all_tags=True)))
    )

    with Comicbox(path, config=config) as car:
        car.dump()

    assert _tag_files(path) == ([], b"")


def test_keep_on_a_pdf_keeps_its_metadata_and_its_comicinfo(tmp_path: Path) -> None:
    path = tmp_path / "cix.pdf"
    shutil.copy(CIX_PDF_SOURCE_PATH, path)
    before = _tags(path)

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert result.written, result.error
    assert _unchanged(before, _tags(path))
    with Comicbox(path) as box:
        carried = box.get_carried_formats().formats
    assert {fmt.name for fmt in carried} == {"COMIC_INFO", "PDF"}


def test_named_and_keep_adds_to_what_the_comic_has(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_MI,), **_TAGS)
    before = _tags(path)

    write_metadata(path, _PATCH, formats=[_CIX, "keep"])

    assert _tag_files(path)[0] == ["comicinfo.xml", "metroninfo.xml"]
    assert _unchanged(before, _tags(path))


def test_keep_leaves_a_format_the_config_does_not_read_byte_for_byte(
    tmp_path: Path,
) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_CIX, _MI), **_TAGS)
    with zipfile.ZipFile(path) as archive:
        metron = archive.read("MetronInfo.xml")
        info = archive.getinfo("MetronInfo.xml")

    result = write_metadata(
        path, _PATCH, formats=["keep"], base_config=_config(**{"read.formats": ["cix"]})
    )

    assert result.written, result.error
    with zipfile.ZipFile(path) as archive:
        assert archive.read("MetronInfo.xml") == metron
        assert archive.getinfo("MetronInfo.xml").CRC == info.CRC
        assert "Kept" in archive.read("ComicInfo.xml").decode()


def test_keep_copies_an_unread_format_into_a_converted_cbz(tmp_path: Path) -> None:
    """A CBT's MetronInfo, unread, goes into its CBZ as it was."""
    path = tmp_path / "comic.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, path)
    with Comicbox(path) as box:
        metron_name = _member(box.namelist(), "MetronInfo.xml")
        metron = box.get_page_by_filename(metron_name)

    result = write_metadata(
        path, _PATCH, formats=["keep"], base_config=_config(**{"read.formats": ["cix"]})
    )

    assert result.written, result.error
    cbz = result.final_path
    assert cbz is not None
    assert cbz == path.with_suffix(".cbz")
    with zipfile.ZipFile(cbz) as archive:
        assert archive.read(metron_name) == metron
        # Rewritten where the comic carries it, not beside it at the root.
        info = _member(archive.namelist(), "ComicInfo.xml")
        assert info == metron_name.replace("metroninfo", "comicinfo")
        assert "Kept" in archive.read(info).decode()


def test_keep_converts_a_cbr_with_its_comment(tmp_path: Path) -> None:
    path = tmp_path / "comic.cbr"
    shutil.copy(CBI_CBR_SOURCE_PATH, path)

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert result.written, result.error
    cbz = result.final_path
    assert cbz is not None
    assert cbz.suffix == ".cbz"
    files, comment = _tag_files(cbz)
    assert files == []
    assert json.loads(comment)["ComicBookInfo/1.0"]["comments"] == "Kept"


def test_keep_with_nothing_to_keep_writes_nothing(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "bare.cbz", formats=(), **_TAGS)
    untouched = path.read_bytes()

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert not result.written
    assert result.error is None
    assert path.read_bytes() == untouched


def test_keep_refuses_a_comic_with_a_tag_file_it_cannot_parse(tmp_path: Path) -> None:
    path = make_comic(
        tmp_path / "broken.cbz",
        files={"ComicInfo.xml": "<ComicInfo><Series>A & B</Series></ComicInfo>"},
        **_TAGS,
    )
    untouched = path.read_bytes()

    result = write_metadata(path, _PATCH, formats=["keep"])

    assert isinstance(result.error, ArchiveWriteError)
    assert "ComicInfo.xml could not be parsed" in str(result.error)
    assert path.read_bytes() == untouched


def test_delete_all_tags_wins_over_keep(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_CIX, _MI), **_TAGS)
    config = _config(**{"write.formats": ["keep"], "write.delete_all_tags": True})

    assert not config.write.keep_formats
    with Comicbox(path, config=config) as box:
        box.dump()

    assert _tag_files(path) == ([], b"")


def test_the_dry_run_payload_holds_every_format_kept(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_CIX, _MI), **_TAGS)
    untouched = path.read_bytes()

    result = write_metadata(path, _PATCH, formats=[JSON, "keep"], dry_run=True)

    assert result.dry_run_payload is not None
    assert set(result.dry_run_payload) == {"COMICBOX_JSON", "COMIC_INFO", "METRON_INFO"}
    assert path.read_bytes() == untouched


def test_bulk_write_keeps_each_comics_own_formats(tmp_path: Path) -> None:
    paths = [
        make_comic(tmp_path / "cix.cbz", formats=(_CIX,), **_TAGS),
        make_comic(tmp_path / "mi.cbz", formats=(_MI,), **_TAGS),
    ]
    items = [BulkWriteItem(path, _PATCH, formats=frozenset({"keep"})) for path in paths]

    results = list(bulk_write(items))

    assert all(result.written for result in results)
    assert _tag_files(paths[0])[0] == ["comicinfo.xml"]
    assert _tag_files(paths[1])[0] == ["metroninfo.xml"]


def test_an_unknown_format_names_keep_among_the_valid(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", **_TAGS)
    with pytest.raises(WriteValidationError, match="or keep"):
        write_metadata(path, _PATCH, formats=["nonsense"])


# ------------------------------------------------------------ the keyword


@pytest.mark.parametrize(
    ("formats", "named", "keep"),
    [
        (["keep"], set(), True),
        (["cix", "keep"], {"COMIC_INFO"}, True),
        (["cix", "KEEP"], {"COMIC_INFO"}, True),
        (["cix"], {"COMIC_INFO"}, False),
    ],
)
def test_the_keyword_on_the_command_line(
    formats: list[str],
    named: set[str],
    keep: bool,
) -> None:
    config = _config(**{"write.formats": formats})
    assert {fmt.name for fmt in config.write.formats} == named
    assert config.write.keep_formats is keep


def test_the_keyword_in_a_config_file(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  write:\n    formats: [cix, keep]\n"
    )
    config = _config()
    assert {fmt.name for fmt in config.write.formats} == {"COMIC_INFO"}
    assert config.write.keep_formats


def test_the_keyword_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A list reaches the environment as indexed variables."""
    monkeypatch.setenv("COMICBOX_WRITE__FORMATS__0", "keep")
    config = _config()
    assert config.write.formats == frozenset()
    assert config.write.keep_formats


def test_a_config_file_cannot_set_keep_formats_directly(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  write:\n    formats: [cix]\n    keep_formats: true\n"
    )
    assert not _config().write.keep_formats


def test_the_main_cli_keeps_with_w_keep(tmp_path: Path) -> None:
    path = make_comic(tmp_path / "cw1.cbz", formats=(_CIX, _MI), **_TAGS)

    code = 0
    try:
        cli.main(("comicbox", "-w", "keep", "-m", "{summary: Kept}", str(path)))
    except SystemExit as exc:
        code = int(exc.code or 0)

    assert code == 0
    assert _tag_files(path)[0] == ["comicinfo.xml", "metroninfo.xml"]
    assert _tags(path)["summary"] == "Kept"


def test_the_doctor_accepts_the_keyword(tmp_path: Path) -> None:
    """No invalid-format warning, no unknown key, and the values validate."""
    from loguru import logger

    from comicbox.doctor.context import DoctorContext
    from comicbox.doctor.result import Status
    from comicbox.doctor.settings import check_unknown_keys, check_values

    (tmp_path / "config.yaml").write_text(
        "comicbox:\n  write:\n    formats: [cix, keep]\n"
    )
    warnings: list[str] = []
    handler = logger.add(warnings.append, level="WARNING", format="{message}")
    try:
        ctx = DoctorContext()
        rows = [*check_values(ctx), *check_unknown_keys(ctx)]
    finally:
        logger.remove(handler)

    assert not [row for row in rows if row.status is not Status.OK]
    assert not [warning for warning in warnings if "invalid format" in warning]
    assert ctx.settings is not None
    assert ctx.settings.write.keep_formats


def test_the_main_cli_stamps_a_keep_write_as_a_named_one(tmp_path: Path) -> None:
    """Keep decides the stamp and the pages as named formats do."""
    named = make_comic(tmp_path / "named" / "cw1.cbz", formats=(_CIX,), **_TAGS)
    kept = make_comic(tmp_path / "kept" / "cw1.cbz", formats=(_CIX,), **_TAGS)

    for path, formats in ((named, "cix"), (kept, "keep")):
        with contextlib.suppress(SystemExit):
            cli.main(("comicbox", "-w", formats, str(path)))

    stamped = _tags(named)
    assert "tagger" in stamped
    assert _tags(kept).keys() == stamped.keys()


# ------------------------------------------------------- R3-G: G1 to G4
