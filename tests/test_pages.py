"""Test getting pages."""

from pathlib import Path

from comicbox.box import Comicbox
from tests.const import TEST_FILES_DIR

ARCHIVE_PATH = TEST_FILES_DIR / "Captain Science #001.cbz"
IMAGE_DIR = TEST_FILES_DIR / "Captain Science 001"
PAGE_TMPL = str(IMAGE_DIR / "CaptainScience#1_{page_num}.jpg")
COVER_IMAGE = Path(PAGE_TMPL.format(page_num="01"))
PAGE_FIVE = Path(PAGE_TMPL.format(page_num="05"))


def test_get_covers():
    """Test getting the cover image."""
    with COVER_IMAGE.open("rb") as cif:
        image = cif.read()
    with Comicbox(ARCHIVE_PATH) as car:
        page = car.get_cover_image()
    assert image == page


def test_get_random_page():
    """Test getting page 5."""
    with Comicbox(ARCHIVE_PATH) as car:
        page = car.get_page_by_index(4)
    with PAGE_FIVE.open("rb") as cif:
        image = cif.read()

    assert image == page


def test_get_pages_after():
    """Test getting many pages."""
    page_num = 33
    with Comicbox(ARCHIVE_PATH) as car:
        pages = car.get_pages(page_num)
    for page in pages:
        path = Path(PAGE_TMPL.format(page_num=page_num + 1))
        with path.open("rb") as cif:
            image = cif.read()
        assert image == page
        page_num += 1
