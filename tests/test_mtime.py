"""Test getting pages."""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from comicbox.box import Comicbox
from tests.const import TEST_FILES_DIR


def _get_stat_mtime(fn: str) -> datetime:
    return datetime.fromtimestamp(
        (TEST_FILES_DIR / fn).stat().st_mtime, tz=timezone.utc
    )


FIXTURES = MappingProxyType(
    {
        "test_pdf.pdf": _get_stat_mtime("test_pdf.pdf"),
        "Captain Science #001-cix-cbi.cbr": _get_stat_mtime(
            "Captain Science #001-cix-cbi.cbr"
        ),
        "Captain Science #001.cbz": datetime(
            2026, 5, 17, 21, 43, 38, tzinfo=timezone.utc
        ),
        # Carries a ComicBookInfo json comment, like the cbr above, so the
        # file's own mtime dates it. It read as the members' date_time
        # while the json check couldn't see a bytes (zip) comment.
        "Captain Science #001 (1950) The Beginning - multi.cbz": _get_stat_mtime(
            "Captain Science #001 (1950) The Beginning - multi.cbz"
        ),
        "empty.cbz": None,
    }
)


@pytest.mark.parametrize("fn", FIXTURES)
def test_get_mtime(fn: str) -> None:
    """Test metadata mtime."""
    path = TEST_FILES_DIR / fn
    with Comicbox(path) as car:
        mtime = car.get_metadata_mtime()
    test_mtime = FIXTURES[fn]
    assert test_mtime == mtime


def test_json_comment_in_a_zip_uses_the_path_mtime(tmp_path: Path) -> None:
    """
    A ComicBookInfo comment is detected on a CBZ, not just a CBR.

    zipfile hands the comment back as bytes and rarfile as a str, and the
    detection indexed it — `b'{'[0]` is 123, matching neither bracket — so
    every zip comment tested as not-json and fell through to the
    archive-file scan, which finds nothing in a comment-only archive.
    """
    cbz = tmp_path / "Comment v1999 #001 (1999).cbz"
    with zipfile.ZipFile(cbz, "w") as zf:
        zf.writestr("CaptainScience#1_01.jpg", b"\xff\xd8\xff\xe0not-really-a-jpeg")
        zf.comment = json.dumps(
            {"appID": "test/1", "ComicBookInfo/1.0": {"series": "Captain Science"}}
        ).encode()

    with Comicbox(cbz) as car:
        assert car._is_comment_json(car._get_archive())
        mtime = car.get_metadata_mtime()
        path_mtime = car.get_path_mtime_dttm()

    # The comment is the metadata, so the file's own mtime dates it. Before,
    # this scanned for metadata files the archive doesn't have and got None.
    assert mtime is not None
    assert mtime == path_mtime
