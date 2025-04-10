"""Test getting pages."""

from argparse import Namespace
from filecmp import cmp

from comicbox.box import Comicbox
from tests.const import CIX_CBZ_SOURCE_PATH, TEST_CS_DIR, TMP_ROOT_DIR
from tests.util import my_cleanup

TMP_DIR = TMP_ROOT_DIR / __name__

EXTRACTED_PAGE_FNS = ("CaptainScience#1_03.jpg", "CaptainScience#1_04.jpg")


def _compare_extract_pages():
    for fn in EXTRACTED_PAGE_FNS:
        good_path = TEST_CS_DIR / fn
        test_path = TMP_DIR / fn

        assert cmp(good_path, test_path)

    my_cleanup(TMP_DIR)


def test_extract_pages():
    """Test extracting pages."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(CIX_CBZ_SOURCE_PATH) as car:
        car.extract_pages(2, 3, TMP_DIR)

    _compare_extract_pages()


def test_extract_pages_config():
    """Test extracting pages with config."""
    TMP_DIR.mkdir(exist_ok=True)
    config = Namespace(comicbox=Namespace(index_from=2, index_to=3, dest_path=str(TMP_DIR)))
    with Comicbox(CIX_CBZ_SOURCE_PATH, config=config) as car:
        car.extract_pages_config()

    _compare_extract_pages()
