"""Test getting pages."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from comicbox.box import Comicbox
from comicbox.box.archive.archive import Archive
from tests.const import CB7_SOURCE_PATH, TEST_FILES_DIR

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


def test_get_page_by_index_out_of_range() -> None:
    """An index past the last page returns None instead of raising."""
    with Comicbox(ARCHIVE_PATH) as car:
        assert car.get_page_by_index(car.get_page_count()) is None


def test_get_pages_after() -> None:
    """
    Test getting many pages.

    B1: consumed after the archive closed, and with every assertion inside
    the loop, an empty generator passed.
    """
    page_from = 3
    with Comicbox(ARCHIVE_PATH) as car:
        pages = list(car.get_pages(page_from))
        page_count = car.get_page_count()
    assert len(pages) == page_count - page_from
    for page_num, page in enumerate(pages, start=page_from + 1):
        path = Path(PAGE_TMPL.format(page_num=f"{page_num:02d}"))
        assert path.read_bytes() == page


def test_get_pages_reads_every_page_by_default() -> None:
    """B1: the default ``page_to`` of -1 read as ``[0:0]``, no pages."""
    with Comicbox(ARCHIVE_PATH) as car:
        pages = list(car.get_pages())
        assert len(pages) == car.get_page_count()
        assert list(car.get_pages(0, -1)) == pages
        assert list(car.get_pages(1, 2)) == pages[1:3]


def test_ignore_macos_resource_forks() -> None:
    """Test ignoring macos resource forks."""
    with Comicbox(RESOURCE_FORK_ARCHIVE) as car:
        page_count = car.get_page_count()
    assert page_count == RESOURCE_FORK_ARCHIVE_PAGE_COUNT


@pytest.mark.parametrize("archive_path", [CB7_SOURCE_PATH, ARCHIVE_PATH])
def test_all_page_reads_match_page_by_page_reads(
    archive_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    C4: an all-pages read of a solid 7z decodes it once, not once a page.

    Read one by one, each page re-decoded the solid block from its start,
    so reading every page cost the square of the page count. The pages
    are byte for byte what a single-page read returns.
    """
    with Comicbox(archive_path) as car:
        count = car.get_page_count()
        expected = [car.get_page_by_index(index) for index in range(count)]
    assert count > 1
    calls: list[int] = []
    real = Archive.extract_7zipfile

    def counting(archive: Any, factory: Any, filenames: Any) -> None:
        calls.append(len(filenames))
        real(archive, factory, filenames)

    monkeypatch.setattr(Archive, "extract_7zipfile", staticmethod(counting))
    out = tmp_path / "pages"
    out.mkdir()

    with Comicbox(archive_path) as car:
        pages = list(car.get_pages())
        car.extract_pages(0, None, out)

    assert pages == expected
    names = sorted(out.iterdir())
    assert [path.read_bytes() for path in names] == expected
    if archive_path.suffix == ".cb7":
        assert calls == [count, count]
