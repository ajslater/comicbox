"""Small generated comic archives, so no test touches a real library."""

from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def make_comic(
    path: Path,
    *,
    series: str,
    number: str,
    start_year: int | None = None,
    volume: int | None = None,
    cover_date: str | None = None,
    ids: dict[str, str] | None = None,
    arcs: dict[str, int | None] | None = None,
) -> Path:
    """Write a CBZ of one page whose comicbox.json holds these tags."""
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("page-0.jpg", b"not-a-real-jpeg")
        archive.writestr("comicbox.json", json.dumps({"comicbox": comic}))
    return path


def digests(directory: Path) -> dict[Path, str]:
    """Hash every file under a directory, to show a run changed none."""
    return {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
