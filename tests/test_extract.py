"""Test getting pages."""

from argparse import Namespace
from filecmp import cmp

import pytest
from pdffile import PDFFile

from comicbox.box import Comicbox
from comicbox.config import get_config
from tests.const import (
    CIX_CBZ_SOURCE_PATH,
    CIX_PDF_SOURCE_PATH,
    PDF_SOURCE_PATH,
    TEST_CS_DIR,
    TEST_FILES_DIR,
    TMP_ROOT_DIR,
)
from tests.util import my_cleanup

TMP_DIR = TMP_ROOT_DIR / __name__

EXTRACTED_PAGE_FNS = ("CaptainScience#1_03.jpg", "CaptainScience#1_04.jpg")
COVER_PATH_SOURCE = TEST_CS_DIR / "CaptainScience#1_01.jpg"
COVER_FN = "cover.jpg"
COVER_PATH_DEST = TMP_DIR / "CaptainScience#1_01.jpg"
PDF_COVER_PATH_SOURCE = TEST_FILES_DIR / "pdf" / "0.pdf"
PDF_COVER_PATH_DEST = TMP_DIR / "0.pdf"
PDF_RANGE_PATH_DEST = TMP_DIR / "1-3.pdf"
PDF_RANGE_FROM = 1
PDF_RANGE_TO = 3
PDF_PAGE_PATH_SOURCE = TEST_FILES_DIR / "pdf" / "1.pdf"
PDF_PAGE_PATH_DEST = TMP_DIR / "1.pdf"
PDF_JPEG_DATA = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
PDF_PAGES_PDF_CONFIG = get_config(
    Namespace(comicbox=Namespace(convert=Namespace(pdf_pages="pdf")))
)
PAGES_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            index_from=2, index_to=3, general=Namespace(dest_path=str(TMP_DIR))
        )
    )
)


def _compare_extract_pages() -> None:
    for fn in EXTRACTED_PAGE_FNS:
        good_path = TEST_CS_DIR / fn
        test_path = TMP_DIR / fn

        assert cmp(good_path, test_path)

    my_cleanup(TMP_DIR)


def test_extract_pages() -> None:
    """Test extracting pages."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(CIX_CBZ_SOURCE_PATH) as car:
        car.extract_pages(2, 3, TMP_DIR)

    _compare_extract_pages()


def test_extract_pages_config() -> None:
    """Test extracting pages with config."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(CIX_CBZ_SOURCE_PATH, config=PAGES_CONFIG) as car:
        car.extract_pages_config()

    _compare_extract_pages()


def test_extract_covers() -> None:
    """Test extract cover."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(CIX_CBZ_SOURCE_PATH) as car:
        car.extract_covers(TMP_DIR)

    assert cmp(COVER_PATH_SOURCE, COVER_PATH_DEST)


def test_extract_cover_pdf() -> None:
    """Test extract cover from pdf."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(PDF_SOURCE_PATH) as car:
        car.extract_covers(TMP_DIR)

    assert cmp(PDF_COVER_PATH_SOURCE, PDF_COVER_PATH_DEST)


def test_extract_pdf_range_as_one_pdf() -> None:
    """Test extracting a range of pdf pages as a single pdf."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(PDF_SOURCE_PATH, config=PDF_PAGES_PDF_CONFIG) as car:
        car.extract_pages(PDF_RANGE_FROM, PDF_RANGE_TO, TMP_DIR)

    with (
        PDFFile(PDF_RANGE_PATH_DEST) as extracted,
        PDFFile(PDF_SOURCE_PATH) as source,
    ):
        page_count = extracted.get_page_count()
        assert page_count == PDF_RANGE_TO - PDF_RANGE_FROM + 1
        # The extracted pages are the source pages, in order.
        for index in range(page_count):
            assert extracted.read_pixmap(index) == source.read_pixmap(
                PDF_RANGE_FROM + index
            )
    my_cleanup(TMP_DIR)


def test_extract_pdf_range_with_embedded_metadata() -> None:
    """Test a range merges even when the pdf embeds a metadata file."""
    # An embedded ComicInfo.xml shares pdffile's namelist with the pages but is
    # not a page, so an open ended range that reaches it still merges the pages.
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(CIX_PDF_SOURCE_PATH, config=PDF_PAGES_PDF_CONFIG) as car:
        car.extract_pages(PDF_RANGE_FROM, None, TMP_DIR)

    assert list(TMP_DIR.iterdir()) == [PDF_RANGE_PATH_DEST]
    with PDFFile(PDF_RANGE_PATH_DEST) as extracted:
        assert extracted.get_page_count() == PDF_RANGE_TO - PDF_RANGE_FROM + 1
    my_cleanup(TMP_DIR)


def test_extract_pdf_single_page_not_merged() -> None:
    """Test that a one page range keeps its page name."""
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(PDF_SOURCE_PATH, config=PDF_PAGES_PDF_CONFIG) as car:
        car.extract_pages(1, 1, TMP_DIR)

    assert cmp(PDF_PAGE_PATH_SOURCE, PDF_PAGE_PATH_DEST)
    my_cleanup(TMP_DIR)


def test_extract_pdf_page_served_as_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a page served as an image is named for its data, not the archive."""
    # Stand in for a reader that hands back a page's big embedded image
    # instead of a one page pdf, but reports no extension for it.
    monkeypatch.setattr(PDFFile, "read", lambda *_args, **_kwargs: PDF_JPEG_DATA)
    TMP_DIR.mkdir(exist_ok=True)
    with Comicbox(PDF_SOURCE_PATH) as car:
        car.extract_pages(0, 0, TMP_DIR)

    assert (TMP_DIR / "0.jpeg").read_bytes() == PDF_JPEG_DATA
    my_cleanup(TMP_DIR)
