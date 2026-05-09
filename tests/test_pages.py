"""Test getting pages."""

from pathlib import Path
from unittest.mock import patch

from comicbox.box import Comicbox
from tests.const import PDF_SOURCE_PATH, TEST_FILES_DIR

ARCHIVE_PATH = TEST_FILES_DIR / "Captain Science #001.cbz"
IMAGE_DIR = TEST_FILES_DIR / "Captain Science 001"
PAGE_TMPL = str(IMAGE_DIR / "CaptainScience#1_{page_num}.jpg")
COVER_IMAGE = Path(PAGE_TMPL.format(page_num="01"))
PAGE_FIVE = Path(PAGE_TMPL.format(page_num="05"))
RESOURCE_FORK_ARCHIVE = TEST_FILES_DIR / "macos_resource_fork.cbz"
RESOURCE_FORK_ARCHIVE_PAGE_COUNT = 2


def test_get_covers() -> None:
    """Test getting the cover image."""
    with COVER_IMAGE.open("rb") as cif:
        image = cif.read()
    with Comicbox(ARCHIVE_PATH) as car:
        page = car.get_cover_page()
    assert image == page


def test_get_cover_skip_metadata() -> None:
    """Skip-metadata path returns the first archive image."""
    with COVER_IMAGE.open("rb") as cif:
        image = cif.read()
    with Comicbox(ARCHIVE_PATH) as car:
        page = car.get_cover_page(skip_metadata=True)
    assert image == page


def test_get_cover_skip_metadata_does_not_read_metadata() -> None:
    """Skip-metadata path must not call get_internal_metadata."""
    with (
        Comicbox(ARCHIVE_PATH) as car,
        patch.object(
            car, "get_internal_metadata", wraps=car.get_internal_metadata
        ) as spy,
    ):
        page = car.get_cover_page(skip_metadata=True)
    assert page
    assert spy.call_count == 0


def test_get_random_page() -> None:
    """Test getting page 5."""
    with Comicbox(ARCHIVE_PATH) as car:
        page = car.get_page_by_index(4)
    with PAGE_FIVE.open("rb") as cif:
        image = cif.read()

    assert image == page


def test_get_pages_after() -> None:
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


def test_ignore_macos_resource_forks() -> None:
    """Test ignoring macos resource forks."""
    with Comicbox(RESOURCE_FORK_ARCHIVE) as car:
        page_count = car.get_page_count()
    assert page_count == RESOURCE_FORK_ARCHIVE_PAGE_COUNT


def test_pdf_hide_text_forwards_to_backend() -> None:
    """``hide_text`` reaches the PDF backend and changes the rendered page."""
    # Page 0 of the fixture is intentionally blank — use page 1 which
    # has text.
    with Comicbox(PDF_SOURCE_PATH) as car:
        baseline = car.get_page_by_index(1, pdf_format="pixmap")
        hidden = car.get_page_by_index(1, pdf_format="pixmap", hide_text=True)
    assert baseline is not None
    assert hidden is not None
    assert baseline != hidden


def test_pdf_hide_text_default_off() -> None:
    """Default ``hide_text=False`` matches the legacy behavior."""
    with Comicbox(PDF_SOURCE_PATH) as car:
        default = car.get_page_by_index(1, pdf_format="pixmap")
        explicit_off = car.get_page_by_index(1, pdf_format="pixmap", hide_text=False)
    assert default == explicit_off


def test_non_pdf_archive_ignores_hide_text() -> None:
    """Non-PDF archives must accept ``hide_text`` and silently ignore it."""
    with Comicbox(ARCHIVE_PATH) as car:
        baseline = car.get_page_by_index(0)
        with_kwarg = car.get_page_by_index(0, hide_text=True)
    assert baseline == with_kwarg
