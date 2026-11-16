"""A RAR or 7z archive named .cbz is refused in one line, not written (B7)."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.exceptions import UnsupportedArchiveTypeError
from comicbox.write import write_metadata
from tests.const import CB7_SOURCE_PATH, CBI_CBR_SOURCE_PATH

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("source", "kind", "suffix"),
    [(CBI_CBR_SOURCE_PATH, "RAR", ".cbr"), (CB7_SOURCE_PATH, "7z", ".cb7")],
    ids=["rar", "7z"],
)
def test_a_misnamed_archive_is_refused_and_left_alone(
    tmp_path: Path, source: Path, kind: str, suffix: str
) -> None:
    """The write called zip methods on it and failed with an AttributeError."""
    path = tmp_path / "comic.cbz"
    shutil.copy(source, path)
    untouched = path.read_bytes()

    result = write_metadata(path, {"summary": "x"}, formats=["COMIC_INFO"])

    assert not result.written
    assert isinstance(result.error, UnsupportedArchiveTypeError)
    assert f"is a {kind} archive named .cbz" in str(result.error)
    assert f"rename it to {suffix}" in str(result.error)
    assert path.read_bytes() == untouched
    assert sorted(p.name for p in tmp_path.iterdir()) == ["comic.cbz"]
    with Comicbox(path) as box:
        assert box.to_dict()["comicbox"]["series"]["name"] == "Captain Science"
