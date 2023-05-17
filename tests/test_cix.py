"""Test CIX module."""
from pathlib import Path

from comicbox.metadata.comicinfoxml import ComicInfoXml

from .test_metadata import TEST_FILES_PATH, TMP_ROOT, read_metadata, write_metadata

FN = Path("Captain Science #001-cix-cbi.cbr")
FN_TAR = Path("Captain Science #001.cbt")
ARCHIVE_PATH = TEST_FILES_PATH / FN
TAR_ARCHIVE_PATH = TEST_FILES_PATH / FN_TAR
TMP_PATH = TMP_ROOT / "test_cix"
NEW_TEST_CBZ_PATH = TMP_PATH / FN.with_suffix(".cbz")
METADATA = {
    "series": "Captain Science",
    "issue": "1",
    "issue_count": 7,
    "publisher": "Youthful Adventure Stories",
    "year": 1950,
    "month": 11,
    "day": 1,
    "volume": 1950,
    "language": "en",
    "web": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
    "characters": frozenset(["Gordon Dane", "Captain Science"]),
    "credits": [
        {"role": "Inker", "person": "Wally Wood"},
        {"role": "Penciller", "person": "Wally Wood"},
        {"role": "Writer", "person": "Joe Orlando"},
    ],
    "ext": "cbr",
    "genres": frozenset(["Science Fiction"]),
    "pages": [
        {"image": "0", "image_size": "429985", "type": "FrontCover"},
        {"image": "1", "image_size": "332936"},
        {"image": "2", "image_size": "458657"},
        {"image": "3", "image_size": "450456"},
        {"image": "4", "image_size": "436648"},
        {"image": "5", "image_size": "443725"},
        {"image": "6", "image_size": "469526"},
        {"image": "7", "image_size": "429811"},
        {"image": "8", "image_size": "445513"},
        {"image": "9", "image_size": "446292"},
        {"image": "10", "image_size": "458589"},
        {"image": "11", "image_size": "417623"},
        {"image": "12", "image_size": "445302"},
        {"image": "13", "image_size": "413271"},
        {"image": "14", "image_size": "434201"},
        {"image": "15", "image_size": "439049"},
        {"image": "16", "image_size": "485957"},
        {"image": "17", "image_size": "388379"},
        {"image": "18", "image_size": "368138"},
        {"image": "19", "image_size": "427874"},
        {"image": "20", "image_size": "422522"},
        {"image": "21", "image_size": "442529"},
        {"image": "22", "image_size": "423785"},
        {"image": "23", "image_size": "427980"},
        {"image": "24", "image_size": "445631"},
        {"image": "25", "image_size": "413615"},
        {"image": "26", "image_size": "417605"},
        {"image": "27", "image_size": "439120"},
        {"image": "28", "image_size": "451598"},
        {"image": "29", "image_size": "451550"},
        {"image": "30", "image_size": "438346"},
        {"image": "31", "image_size": "454914"},
        {"image": "32", "image_size": "428461"},
        {"image": "33", "image_size": "438091"},
        {"image": "34", "image_size": "353013"},
        {"image": "35", "image_size": "340840"},
    ],
    "page_count": 36,
    "cover_image": "Captain Science 001/CaptainScience#1_01.jpg",
    "story_arcs": {
        "Captain Arc": 4,
        "Other Arc": 2,
    },
}


def test_read_cix_rar():
    """Read RAR with CIX."""
    read_metadata(ARCHIVE_PATH, METADATA)


def text_read_cix_tar():
    """Read Tarball with CIX."""
    read_metadata(TAR_ARCHIVE_PATH, METADATA)


def test_write_cix_from_rar():
    """Write cbz with CIX."""
    write_metadata(TMP_PATH, NEW_TEST_CBZ_PATH, METADATA, ComicInfoXml)
