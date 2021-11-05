from comicbox.comic_archive import ComicArchive

from .test_metadata import TEST_FILES_PATH


ARCHIVE_PATH = TEST_FILES_PATH / "Captain Science #001.cbz"
IMAGE_DIR = TEST_FILES_PATH / "Captain Science 001"
PAGE_TMPL = str(IMAGE_DIR / "CaptainScience#1_{page_num}.jpg")
COVER_IMAGE = PAGE_TMPL.format(page_num="01")


def test_get_covers():
    car = ComicArchive(ARCHIVE_PATH, get_cover=True)
    with open(COVER_IMAGE, "rb") as cif:
        image = cif.read()

    assert image == car.cover_image_data
