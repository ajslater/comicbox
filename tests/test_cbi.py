"""Test CBI module."""
from pathlib import Path

from comicbox.metadata.comicbookinfo import ComicBookInfo

from .test_metadata import TEST_FILES_PATH
from .test_metadata import TMP_ROOT
from .test_metadata import read_metadata
from .test_metadata import write_metadata


FN = Path("Captain Science #001-cbi.cbr")
ARCHIVE_PATH = TEST_FILES_PATH / FN
TMP_PATH = TMP_ROOT / "test_cbi"
NEW_TEST_CBZ_PATH = TMP_PATH / FN.with_suffix(".cbz")
METADATA = {
    "series": "Captain Science",
    "issue": "1",
    "issue_count": 7,
    "publisher": "Youthful Adventure Stories",
    "month": 11,
    "year": 1950,
    "genres": set(["Science Fiction"]),
    "volume": 1950,
    "credits": [
        {"person": "Wally Wood", "role": "Artist"},
        {"person": "Joe Orlando", "role": "Writer", "primary": True},
    ],
    "language": "en",
    "country": "US",
    "title": "The Beginning",
    "page_count": 36,
    "cover_image": "Captain Science 001/CaptainScience#1_01.jpg",
    "ext": "cbr",
    # "remainder": "cbi",
}


def test_read_cbi():
    read_metadata(ARCHIVE_PATH, METADATA)


def test_write_cbi():
    write_metadata(TMP_PATH, NEW_TEST_CBZ_PATH, METADATA, ComicBookInfo)
