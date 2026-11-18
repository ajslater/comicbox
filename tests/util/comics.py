"""Small generated comic archives, so no test touches a real library."""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

JSON = "COMICBOX_JSON"


def comic_tags(
    *, series: str, number: str, volume: int | None = None
) -> dict[str, Any]:
    """Build the comicbox tags of one comic."""
    comic: dict[str, Any] = {"series": {"name": series}, "issue": {"name": number}}
    if volume is not None:
        comic["volume"] = {"number": volume}
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
