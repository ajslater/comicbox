"""Test getting pages."""
from pathlib import Path

from comicbox.comic_archive import ComicArchive

from .test_metadata import TEST_FILES_PATH


ARCHIVE_PATH = TEST_FILES_PATH / "Captain Science #001.cbz"
IMAGE_DIR = TEST_FILES_PATH / "Captain Science 001"
PAGE_TMPL = str(IMAGE_DIR / "CaptainScience#1_{page_num}.jpg")
COVER_IMAGE = PAGE_TMPL.format(page_num="01")
PAGE_FIVE = PAGE_TMPL.format(page_num="05")


def test_get_covers():
    """Test getting the cover image."""
    with open(COVER_IMAGE, "rb") as cif:
        image = cif.read()
    with ComicArchive(ARCHIVE_PATH) as car:
        page = car.get_cover_image()
    assert image == page


def test_get_random_page():
    """Test getting page 5."""
    car = ComicArchive(ARCHIVE_PATH)
    page = car.get_page_by_index(4)
    with open(PAGE_FIVE, "rb") as cif:
        image = cif.read()

    assert image == page


def test_get_pages_after():
    """Test getting many pages."""
    car = ComicArchive(ARCHIVE_PATH)
    page_num = 33
    pages = car.get_pages(page_num)
    for page in pages:
        fn = Path(PAGE_TMPL.format(page_num=page_num + 1))
        with open(fn, "rb") as cif:
            image = cif.read()
        assert image == page
        page_num += 1
