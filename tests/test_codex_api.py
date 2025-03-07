"""Test the API surface that Codex uses."""

from argparse import Namespace
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from pprint import pprint
from types import MappingProxyType

import fitz
import pytest
from deepdiff.diff import DeepDiff

from comicbox.box import Comicbox
from comicbox.box.computed import deep_update
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.version import VERSION
from tests.const import (
    CIX_CBI_CBR_SOURCE_PATH,
    CIX_CBT_SOURCE_PATH,
    CIX_CBZ_SOURCE_PATH,
    PDF_SOURCE_PATH,
    TEST_DATETIME,
    TEST_FILES_DIR,
    TEST_READ_NOTES,
)


@dataclass
class Fixture:
    """Test results."""

    path: Path
    page_count: int
    metadata: MappingProxyType
    files_path: str
    cover_path: str


CBZ_MD = MappingProxyType(
    {
        ROOT_TAG: {
            "characters": {"Captain Science", "Gordon Dane"},
            "contributors": {
                "inker": {"Wally Wood"},
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": TEST_READ_NOTES,
            "page_count": 36,
            "pages": [
                {"index": 0, "page_type": PageTypeEnum.FRONT_COVER, "size": 429985},
                {"index": 1, "size": 332936},
                {"index": 2, "size": 458657},
                {"index": 3, "size": 450456},
                {"index": 4, "size": 436648},
                {"index": 5, "size": 443725},
                {"index": 6, "size": 469526},
                {"index": 7, "size": 429811},
                {"index": 8, "size": 445513},
                {"index": 9, "size": 446292},
                {"index": 10, "size": 458589},
                {"index": 11, "size": 417623},
                {"index": 12, "size": 445302},
                {"index": 13, "size": 413271},
                {"index": 14, "size": 434201},
                {"index": 15, "size": 439049},
                {"index": 16, "size": 485957},
                {"index": 17, "size": 388379},
                {"index": 18, "size": 368138},
                {"index": 19, "size": 427874},
                {"index": 20, "size": 422522},
                {"index": 21, "size": 442529},
                {"index": 22, "size": 423785},
                {"index": 23, "size": 427980},
                {"index": 24, "size": 445631},
                {"index": 25, "size": 413615},
                {"index": 26, "size": 417605},
                {"index": 27, "size": 439120},
                {"index": 28, "size": 451598},
                {"index": 29, "size": 451550},
                {"index": 30, "size": 438346},
                {"index": 31, "size": 454914},
                {"index": 32, "size": 428461},
                {"index": 33, "size": 438091},
                {"index": 34, "size": 353013},
                {"index": 35, "size": 340840},
            ],
            "publisher": "Youthful Adventure Stories",
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science Alternate"}}
            ],
            "series": {"name": "Captain Science"},
            "story_arcs": {"Captain Arc": 4, "Other Arc": 2},
            "title": "The Beginning",
            "tagger": f"comicbox {VERSION}",
            "updated_at": TEST_DATETIME,
            "volume": {"name": 1950, "issue_count": 7},
            "year": 1950,
        }
    }
)
CBR_MD_PATCH = {
    ROOT_TAG: {
        "country": "US",
        "ext": "cbr",
        "series": {"volume_count": 1},
        "title": "The Beginning",
    },
}
CBR_MD = MappingProxyType(deep_update(deepcopy(dict(CBZ_MD)), CBR_MD_PATCH))
CBT_MD_PATCH = {
    ROOT_TAG: {
        "ext": "cbt",
        "page_count": 5,
        "pages": [
            {"index": 0, "page_type": PageTypeEnum.FRONT_COVER, "size": 429985},
            {"index": 1, "size": 332936},
            {"index": 2, "size": 458657},
            {"index": 3, "size": 450456},
            {"index": 4, "size": 436648},
        ],
    }
}
CBT_MD = MappingProxyType(deep_update(deepcopy(dict(CBZ_MD)), CBT_MD_PATCH))
PDF_MD = MappingProxyType(
    {
        ROOT_TAG: {
            "contributors": {"writer": {"Jon Osterman"}},
            "ext": "pdf",
            "genres": {"Science Fiction"},
            "page_count": 4,
            "scan_info": "Pages",
            "series": {"name": "test pdf"},
            "tags": {"d", "f", "e"},
            "title": "the tangle of their lives",
            "tagger": f"comicbox {VERSION}",
            "publisher": "SmallPub",
        }
    }
)

CS = "Captain Science 001"
CS_COVER = CS + "/CaptainScience#1_01.jpg"
FIXTURES = MappingProxyType(
    {
        "CBZ": Fixture(CIX_CBZ_SOURCE_PATH, 36, CBZ_MD, CS, CS_COVER),
        "CBR": Fixture(CIX_CBI_CBR_SOURCE_PATH, 36, CBR_MD, CS, CS_COVER),
        "CBT": Fixture(CIX_CBT_SOURCE_PATH, 5, CBT_MD, CS, CS_COVER),
        "PDF": Fixture(PDF_SOURCE_PATH, 4, PDF_MD, "pdf", "pdf/0.pdf"),
    }
)
INDEXES = (2, 0, 1, 3)


def test_check_unrar():
    """Test the check unrar exec method."""
    checked = False
    try:
        Comicbox.check_unrar_executable()
        checked = True
    except Exception as exc:
        print(exc)
    assert checked


@pytest.mark.parametrize("ft", FIXTURES)
def test_codex_import(ft):
    """Test codex import methods."""
    fixture = FIXTURES[ft]
    ns = Namespace(comicbox=Namespace(print="s"))
    with Comicbox(fixture.path, config=ns) as car:
        car_ft = car.get_file_type()
        car_md = MappingProxyType(car.get_metadata())
        car_count = car.get_page_count()
        car.print_out()
    assert car_ft == ft
    assert car_count == fixture.page_count
    pprint(fixture.metadata)
    pprint(car_md)
    diff = DeepDiff(fixture.metadata, car_md)
    pprint(diff)
    assert not diff


@pytest.mark.parametrize("ft", FIXTURES)
def test_cover_image(ft):
    """Test codex cover extraction methods."""
    fixture = FIXTURES[ft]
    with Comicbox(fixture.path) as car:
        cover = car.get_cover_image()
    cover_path = Path(TEST_FILES_DIR / fixture.cover_path)
    print(f"{cover_path=}")
    with cover_path.open("rb") as f:
        disk_cover = f.read()
    if cover_path.suffix == ".pdf":
        # transform file to image.
        try:
            doc = fitz.Document(stream=disk_cover)
            pix = doc.get_page_pixmap(0)  # type: ignore[reportAttributeAccessIssue]
            disk_cover = pix.tobytes(output="ppm")
        except NameError as exc:
            reason = "fitz not imported from pymupdf (comicbox-pdffile)"
            raise AssertionError(reason) from exc

    assert cover == disk_cover


@pytest.mark.parametrize("ft", FIXTURES)
def test_random_access_page(ft):
    """Test codex get page image methods."""
    fixture = FIXTURES[ft]
    files = sorted(Path(TEST_FILES_DIR / fixture.files_path).iterdir())
    print("path", fixture.path)
    with Comicbox(fixture.path) as car:
        print("page count:", car.get_page_count())
        for index in INDEXES:
            print(f"{index=}")
            page = car.get_page_by_index(index)
            page_path = files[index]
            with page_path.open("rb") as f:
                disk_page = f.read()
            print(f"{page_path=}")
            # with Path( "/tmp/" / Path(page_path.name) ).open("wb") as f:
            #    f.write(page) # noqa: ERA001
            assert disk_page == page
