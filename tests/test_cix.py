"""Test CIX module."""
from pathlib import Path

from comicbox.metadata.comicinfoxml import ComicInfoXml

from .test_metadata import TEST_FILES_PATH
from .test_metadata import TMP_ROOT
from .test_metadata import read_metadata
from .test_metadata import write_metadata


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
    "characters": set(["Gordon Dane", "Captain Science"]),
    "credits": [
        {"person": "Joe Orlando", "role": "Writer"},
        {"person": "Wally Wood", "role": "Penciller"},
        {"person": "Wally Wood", "role": "Inker"},
    ],
    "ext": "cbr",
    "genres": set(["Science Fiction"]),
    "pages": [
        {"Image": "0", "ImageSize": "429985", "Type": "FrontCover"},
        {"Image": "1", "ImageSize": "332936"},
        {"Image": "2", "ImageSize": "458657"},
        {"Image": "3", "ImageSize": "450456"},
        {"Image": "4", "ImageSize": "436648"},
        {"Image": "5", "ImageSize": "443725"},
        {"Image": "6", "ImageSize": "469526"},
        {"Image": "7", "ImageSize": "429811"},
        {"Image": "8", "ImageSize": "445513"},
        {"Image": "9", "ImageSize": "446292"},
        {"Image": "10", "ImageSize": "458589"},
        {"Image": "11", "ImageSize": "417623"},
        {"Image": "12", "ImageSize": "445302"},
        {"Image": "13", "ImageSize": "413271"},
        {"Image": "14", "ImageSize": "434201"},
        {"Image": "15", "ImageSize": "439049"},
        {"Image": "16", "ImageSize": "485957"},
        {"Image": "17", "ImageSize": "388379"},
        {"Image": "18", "ImageSize": "368138"},
        {"Image": "19", "ImageSize": "427874"},
        {"Image": "20", "ImageSize": "422522"},
        {"Image": "21", "ImageSize": "442529"},
        {"Image": "22", "ImageSize": "423785"},
        {"Image": "23", "ImageSize": "427980"},
        {"Image": "24", "ImageSize": "445631"},
        {"Image": "25", "ImageSize": "413615"},
        {"Image": "26", "ImageSize": "417605"},
        {"Image": "27", "ImageSize": "439120"},
        {"Image": "28", "ImageSize": "451598"},
        {"Image": "29", "ImageSize": "451550"},
        {"Image": "30", "ImageSize": "438346"},
        {"Image": "31", "ImageSize": "454914"},
        {"Image": "32", "ImageSize": "428461"},
        {"Image": "33", "ImageSize": "438091"},
        {"Image": "34", "ImageSize": "353013"},
        {"Image": "35", "ImageSize": "340840"},
    ],
    # "remainder": "cix cbi",
    "page_count": 36,
    "cover_image": "Captain Science 001/CaptainScience#1_01.jpg",
}


def test_read_cix_rar():
    read_metadata(ARCHIVE_PATH, METADATA)


def text_read_cix_tar():
    read_metadata(TAR_ARCHIVE_PATH, METADATA)


def test_write_cix_from_rar():
    write_metadata(TMP_PATH, NEW_TEST_CBZ_PATH, METADATA, ComicInfoXml)
