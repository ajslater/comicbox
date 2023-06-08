"""Tests for writing."""
import shutil
from pathlib import Path

from comicbox.comic_archive import ComicArchive
from comicbox.metadata.comicinfoxml import ComicInfoXml

from .test_metadata import TEST_FILES_PATH, TMP_ROOT, read_metadata

FN = Path("Captain Science #001-cbi.cbr")
ARCHIVE_PATH = TEST_FILES_PATH / FN
TMP_PATH = TMP_ROOT / "test_write"
OLD_TEST_CBR_PATH = TMP_PATH / FN
NEW_TEST_CBZ_PATH = TMP_PATH / FN.with_suffix(".cbz")

METADATA = {
    "cover_image": "Captain Science 001/CaptainScience#1_01.jpg",
    "credits": [
        {"person": "Wally Wood", "role": "Inker"},
        {"person": "Wally Wood", "role": "Penciller"},
        {"person": "Joe Orlando", "role": "Writer"},
    ],
    "ext": "cbz",
    "genres": frozenset({"Science Fiction"}),
    "issue": "1",
    "issue_count": 7,
    "language": "en",
    "month": 11,
    "page_count": 36,
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
    "publisher": "Youthful Adventure Stories",
    "series": "Captain Science",
    "title": "The Beginning",
    "volume": 1950,
    "year": 1950,
    "tags": frozenset(["a", "b", "c"]),
}


def setup():
    """Set up test dir and copy archive."""
    shutil.rmtree(TMP_PATH, ignore_errors=True)
    TMP_PATH.mkdir(parents=True, exist_ok=True)
    shutil.copy(ARCHIVE_PATH, OLD_TEST_CBR_PATH)


def cleanup():
    """Cleanup test dir."""
    shutil.rmtree(TMP_PATH)


def test_convert_to_cbz_and_cbi_to_cix():
    """Test converting cbr to cbz and writing cbi info as cix."""
    setup()

    md = {"tags": frozenset(["a", "b", "c"])}

    # read and write
    # inject tags.
    with ComicArchive(OLD_TEST_CBR_PATH) as car:
        car.add_metadata(md)
        car.write_metadata(ComicInfoXml)

    # test
    read_metadata(NEW_TEST_CBZ_PATH, METADATA)

    cleanup()
