"""Test the API surface that Codex uses."""

from argparse import Namespace
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pymupdf
import pytest

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.merge import AdditiveMerger
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.version import VERSION
from tests.const import (
    CB7_SOURCE_PATH,
    CIX_CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    PDF_SOURCE_PATH,
    TEST_DATETIME,
    TEST_FILES_DIR,
    TEST_METADATA_DIR,
    TEST_READ_NOTES,
)
from tests.util import assert_diff

CONFIG = get_config(Namespace(comicbox=Namespace(print="sc")))


@dataclass
class Fixture:
    """Test results."""

    path: Path
    page_count: int
    metadata: MappingProxyType
    files_path: str
    cover_path: str
    cover_path_list: tuple[str, ...]


TEMPLATE_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
            "age_rating": "Teen",
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "date": {
                "cover_date": date(1950, 11, 1),
                "day": 1,
                "month": 11,
                "year": 1950,
            },
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": {
                "name": "1",
                "number": Decimal("1"),
            },
            "language": "en",
            "notes": TEST_READ_NOTES,
            "page_count": 36,
            "pages": {
                0: {"page_type": PageTypeEnum.FRONT_COVER, "size": 429985},
                1: {"size": 332936},
                2: {"size": 458657},
                3: {"size": 450456},
                4: {"size": 436648},
                5: {"size": 443725},
                6: {"size": 469526},
                7: {"size": 429811},
                8: {"size": 445513},
                9: {"size": 446292},
                10: {"size": 458589},
                11: {"size": 417623},
                12: {"size": 445302},
                13: {"size": 413271},
                14: {"size": 434201},
                15: {"size": 439049},
                16: {"size": 485957},
                17: {"size": 388379},
                18: {"size": 368138},
                19: {"size": 427874},
                20: {"size": 422522},
                21: {"size": 442529},
                22: {"size": 423785},
                23: {"size": 427980},
                24: {"size": 445631},
                25: {"size": 413615},
                26: {"size": 417605},
                27: {"size": 439120},
                28: {"size": 451598},
                29: {"size": 451550},
                30: {"size": 438346},
                31: {"size": 454914},
                32: {"size": 428461},
                33: {"size": 438091},
                34: {"size": 353013},
                35: {"size": 340840},
            },
            "publisher": {"name": "Youthful Adventure Stories"},
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science Alternate"}}
            ],
            "series": {"name": "Captain Science"},
            "tagger": f"comicbox {VERSION}",
            "title": "The Beginning; The End",
            "updated_at": TEST_DATETIME,
            "volume": {"number": 1950, "issue_count": 7},
        }
    }
)


def _patch_md(patch):
    res = {}
    AdditiveMerger.merge(res, TEMPLATE_MD, patch)
    return MappingProxyType(res)


CBZ_MD_PATCH = {
    ComicboxSchemaMixin.ROOT_TAG: {
        "stories": {
            "The Beginning": {},
            "The End": {},
        },
        "page_count": 36,
    }
}
CBZ_MD = _patch_md(CBZ_MD_PATCH)

CBR_MD_PATCH = {
    ComicboxSchemaMixin.ROOT_TAG: {
        "country": "US",
        "ext": "cbr",
        "series": {"volume_count": 1},
        "stories": {
            "The Beginning": {},
            "The End": {},
        },
    },
}
CBR_MD = _patch_md(CBR_MD_PATCH)
CBT_MD_PATCH = {
    ComicboxSchemaMixin.ROOT_TAG: {
        "ext": "cbt",
        "identifier_primary_source": {
            "source": "comicvine",
            "url": "https://comicvine.gamespot.com/",
        },
        "identifiers": {
            "comicvine": {
                "key": "145269",
                "url": "https://comicvine.gamespot.com/c/4000-145269/",
            },
            "isbn": {
                "key": "123-456789-0123",
                "url": "https://isbndb.com/book/123-456789-0123",
            },
            "upc": {"key": "12345", "url": "https://barcodelookup.com/12345"},
        },
        "date": {"cover_date": date(1950, 11, 1)},
        "notes": (
            "Tagged with "
            "comicbox dev "
            "on "
            "1970-01-01T00:00:00Z "
            "[Issue ID "
            "145269] "
            "urn:comicvine:4000-145269 "
            "urn:isbn:123-456789-0123 "
            "urn:upc:12345"
        ),
        "page_count": 5,
        "stories": {
            "The Beginning": {},
            "The End": {},
        },
    }
}
CBT_MD = _patch_md(CBT_MD_PATCH)
PDF_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "ext": "pdf",
            "genres": {"Science Fiction": {}},
            "notes": "Tagged with comicbox dev on 2025-05-22T03:12:25Z",
            "page_count": 4,
            "scan_info": "Pages",
            "series": {"name": "test pdf"},
            "stories": {"the tangle of their lives": {}},
            "tags": {"d": {}, "e": {}, "f": {}},
            "title": "the tangle of their lives",
            "tagger": "comicbox dev",
            "publisher": {"name": "SmallPub"},
            "updated_at": datetime(2025, 5, 22, 3, 12, 25, tzinfo=timezone.utc),
        }
    }
)

CB7_MD_PATCH = {
    ComicboxSchemaMixin.ROOT_TAG: {
        "date": {
            "cover_date": date(1950, 11, 1),
        },
        "ext": "cb7",
        "page_count": 5,
        "identifier_primary_source": {
            "source": "comicvine",
            "url": "https://comicvine.gamespot.com/",
        },
        "identifiers": {
            "comicvine": {
                "key": "145269",
                "url": "https://comicvine.gamespot.com/c/4000-145269/",
            },
            "isbn": {
                "key": "123-456789-0123",
                "url": "https://isbndb.com/book/123-456789-0123",
            },
            "upc": {"key": "12345", "url": "https://barcodelookup.com/12345"},
        },
        "notes": (
            "Tagged with comicbox dev on 1970-01-01T00:00:00Z "
            "[Issue ID 145269] urn:comicvine:4000-145269 "
            "urn:isbn:123-456789-0123 urn:upc:12345"
        ),
        "stories": {"The Beginning": {}, "The End": {}},
    }
}
CB7_MD = _patch_md(CB7_MD_PATCH)

CS = "Captain Science 001"
CS_COVER = CS + "/CaptainScience#1_01.jpg"
CS_COVER_PATH_LIST = (CS_COVER,)
FIXTURES = MappingProxyType(
    {
        "CBZ": Fixture(
            CIX_CBZ_SOURCE_PATH, 36, CBZ_MD, CS, CS_COVER, CS_COVER_PATH_LIST
        ),
        "CBR": Fixture(
            CIX_CBI_CBR_SOURCE_PATH, 36, CBR_MD, CS, CS_COVER, CS_COVER_PATH_LIST
        ),
        "CBT": Fixture(
            CIX_CBT_SOURCE_PATH, 5, CBT_MD, CS, CS_COVER, CS_COVER_PATH_LIST
        ),
        "PDF": Fixture(PDF_SOURCE_PATH, 4, PDF_MD, "pdf", "pdf/0.pdf", ("0",)),
        "CB7": Fixture(CB7_SOURCE_PATH, 5, CB7_MD, CS, CS_COVER, CS_COVER_PATH_LIST),
    }
)
INDEXES = (2, 0, 1, 3)


def test_check_unrar():
    """Test the check unrar exec method."""
    Comicbox.check_unrar_executable()
    assert True


@pytest.mark.parametrize("ft", FIXTURES)
def test_codex_import(ft):
    """Test codex import methods."""
    fixture = FIXTURES[ft]
    with Comicbox(fixture.path, config=CONFIG) as car:
        car_ft = car.get_file_type()
        car_md = MappingProxyType(car.get_metadata())
        car_count = car.get_page_count()
        # car.print_out() debug
    assert car_ft == ft
    assert car_count == fixture.page_count
    assert_diff(fixture.metadata, car_md)


@pytest.mark.parametrize("ft", FIXTURES)
def test_cover_page(ft):
    """Test codex cover extraction methods."""
    fixture = FIXTURES[ft]
    cover_path = Path(TEST_FILES_DIR / fixture.cover_path)
    is_pdf = cover_path.suffix == ".pdf"
    with Comicbox(fixture.path, config=CONFIG) as car:
        cover = car.get_cover_page(to_pixmap=is_pdf)
    with cover_path.open("rb") as f:
        disk_cover = f.read()
    if is_pdf:
        # transform file to image.
        try:
            doc = pymupdf.Document(stream=disk_cover)
            pix = doc.get_page_pixmap(0)  # pyright: ignore[reportAttributeAccessIssue]
            disk_cover = pix.tobytes(output="ppm")
        except NameError as exc:
            reason = "fitz not imported from pymupdf (comicbox-pdffile)"
            raise AssertionError(reason) from exc

    if cover != disk_cover:
        print(f"{cover_path=}")  # noqa: T201
    assert cover == disk_cover


_COVER_PATH_LIST = (
    "Captain Science 001/CaptainScience#1_01.jpg",
    "Captain Science 001/CaptainScience#1_03.jpg",
    "Captain Science 001/CaptainScience#1_02.jpg",
)
_COVER_PATH_LIST_IMPORTS = (
    TEST_METADATA_DIR / "comicinfo-cover-path-list.xml",
    TEST_METADATA_DIR / "comet-cover-path-list.xml",
)


def test_cover_paths():
    """Test codex cover path lists."""
    config = Namespace(comicbox=Namespace(import_paths=_COVER_PATH_LIST_IMPORTS))
    with Comicbox(CIX_CBZ_SOURCE_PATH, config=config) as car:
        cover_path_list = car.get_cover_paths()
    assert_diff(_COVER_PATH_LIST, cover_path_list)


@pytest.mark.parametrize("ft", FIXTURES)
def test_random_access_page(ft):
    """Test codex get page image methods."""
    fixture = FIXTURES[ft]
    files = sorted(Path(TEST_FILES_DIR / fixture.files_path).iterdir())
    with Comicbox(fixture.path, config=CONFIG) as car:
        for index in INDEXES:
            page = car.get_page_by_index(index)
            page_path = files[index]
            with page_path.open("rb") as f:
                disk_page = f.read()
            # with Path( "/tmp/" / Path(page_path.name) ).open("wb") as f:
            #   f.write(page) # noqa: ERA001
            if disk_page != page:
                print(f"{fixture.path=} {car.get_page_count()} {index=} {page_path=}")  # noqa: T201
            assert disk_page == page
