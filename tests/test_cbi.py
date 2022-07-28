"""Test CBI module."""
from pathlib import Path

from comicbox.metadata.comicbookinfo import ComicBookInfo

from .test_metadata import TEST_FILES_PATH, TMP_ROOT, read_metadata, write_metadata


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
    "genres": frozenset(["Science Fiction"]),
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
}


def test_read_cbi():
    """Read CBI archive."""
    read_metadata(ARCHIVE_PATH, METADATA)


def test_write_cbi():
    """Write CBI archive."""
    write_metadata(TMP_PATH, NEW_TEST_CBZ_PATH, METADATA, ComicBookInfo)
