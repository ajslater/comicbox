"""Small generated comic archives, so no test touches a real library."""

from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

JSON = "COMICBOX_JSON"


def comic_tags(
    *,
    series: str,
    number: str,
    start_year: int | None = None,
    volume: int | None = None,
    cover_date: str | None = None,
    ids: dict[str, str] | None = None,
    arcs: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """Build the comicbox tags of one comic."""
    series_tags: dict[str, Any] = {"name": series}
    if start_year is not None:
        series_tags["start_year"] = start_year
    comic: dict[str, Any] = {"series": series_tags, "issue": {"name": number}}
    if volume is not None:
        comic["volume"] = {"number": volume}
    if cover_date is not None:
        comic["date"] = {"cover_date": cover_date}
    if ids:
        comic["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    if arcs:
        comic["arcs"] = {
            name: {} if arc_number is None else {"number": arc_number}
            for name, arc_number in arcs.items()
        }
    return comic


def make_comic(
    path: Path,
    *,
    formats: Sequence[str] = (JSON,),
    files: Mapping[str, str] | None = None,
    comment: str | None = None,
    **tags: Any,
) -> Path:
    """
    Write a CBZ of one page holding these tags in each of ``formats``.

    ``formats`` are ``MetadataFormats`` names; ComicBookInfo goes in the
    archive comment and the rest in their files. ``files`` adds raw files,
    such as a broken tag file, and ``comment`` sets the archive comment.
    """
    comic = comic_tags(**tags)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("page-0.jpg", b"not-a-real-jpeg")
        for name in formats:
            if name == JSON:
                archive.writestr("comicbox.json", json.dumps({"comicbox": comic}))
                continue
            from comicbox.box import Comicbox
            from comicbox.formats import MetadataFormats

            fmt = MetadataFormats[name]
            text = Comicbox(metadata={"comicbox": comic}).to_string(fmt)
            if fmt is MetadataFormats.COMIC_BOOK_INFO:
                archive.comment = text.encode()
            else:
                archive.writestr(fmt.value.filename, text)
        for name, text in (files or {}).items():
            archive.writestr(name, text)
        if comment is not None:
            archive.comment = comment.encode()
    return path


def tag_files(path: Path) -> list[str]:
    """List a CBZ's members other than its page."""
    with zipfile.ZipFile(path) as archive:
        return sorted(name for name in archive.namelist() if name != "page-0.jpg")


def digests(directory: Path) -> dict[Path, str]:
    """Hash every file under a directory, to show a run changed none."""
    return {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
