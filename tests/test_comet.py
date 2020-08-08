"""Test CIX module."""
from decimal import Decimal

from comicbox.metadata.comet import CoMet

from .test_metadata import TEST_FILES_PATH
from .test_metadata import TMP_ROOT
from .test_metadata import read_metadata
from .test_metadata import write_metadata


ARCHIVE_PATH = TEST_FILES_PATH / "Captain Science #001-comet.cbz"
TMP_PATH = TMP_ROOT / "test_comet"
NEW_TEST_CBZ_PATH = TMP_PATH / "test_comet_write_001-comet.cbz"
METADATA = {
    "series": "Captain Science",
    "issue": 1,
    "publisher": "Bell Features",
    "year": 1950,
    "month": 12,
    "day": 1,
    "volume": 1,
    "language": "en",
    "characters": set(["Captain Science", "Gordon Dane"]),
    "credits": [
        {"person": "Joe Orlando", "role": "writer"},
        {"person": "Wally Wood", "role": "penciller"},
    ],
    "ext": "cbz",
    "genre": "Science Fiction",
    "description": "A long example description",
    "is_version_of": "Captain Science",
    "price": Decimal(0.10).quantize(Decimal("0.01")),
    "format": "Comic",
    "maturity_rating": "Teen",
    "rights": "Copyright (c) 1950 Bell Features",
    "identifier": "4000-145269",
    "reading_direction": "ltr",
    "title": "The Beginning",
    "last_mark": 12,
    "cover_image": "CaptainScience#1_01.jpg",
    "remainder": "comet",
    "page_count": 36,
}


def test_read_comet():
    read_metadata(ARCHIVE_PATH, METADATA)


def test_write_comet():
    write_metadata(TMP_PATH, NEW_TEST_CBZ_PATH, METADATA, CoMet)
