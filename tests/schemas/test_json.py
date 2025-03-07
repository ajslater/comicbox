"""Test CBI module."""

from argparse import Namespace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import simplejson as json

from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.schemas.comicbox_json import ComicboxJsonSchema
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from tests.const import TEST_DATETIME, TEST_DTTM_STR, TEST_READ_NOTES
from tests.util import TestParser, create_write_dict, create_write_metadata

FN = Path("comicbox.cbz")
READ_CONFIG = Namespace(comicbox=Namespace(read=["cb"], compute_pages=False))
WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=["cb"], read=["cb"], compute_pages=False)
)
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "country": "US",
            "series": {"name": "Captain Science"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "publisher": "Youthful Adventure Stories",
            "month": 11,
            "year": 1950,
            "day": 1,
            "genres": {"Science Fiction"},
            "volume": {
                "name": 1950,
                "issue_count": 7,
            },
            "contributors": {
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "language": "en",
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": TEST_DATETIME,
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
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_COMICBOX_DICT = MappingProxyType(
    {
        "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json",
        "appID": "comicbox/dev",
        ComicboxJsonSchema.ROOT_TAGS[0]: {
            "country": "US",
            "contributors": {
                "penciller": ["Wally Wood"],
                "writer": ["Joe Orlando"],
            },
            "day": 1,
            "genres": ["Science Fiction"],
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": TEST_READ_NOTES,
            "page_count": 36,
            "publisher": "Youthful Adventure Stories",
            "series": {"name": "Captain Science"},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": TEST_DTTM_STR,
            "volume": {
                "name": 1950,
                "issue_count": 7,
            },
            "year": 1950,
            "pages": [
                {
                    "index": 0,
                    "page_type": PageTypeEnum.FRONT_COVER.value,
                    "size": 429985,
                },
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
        },
    }
)
WRITE_COMICBOX_DICT = create_write_dict(READ_COMICBOX_DICT, ComicboxJsonSchema, "notes")
READ_COMICBOX_STR = json.dumps(
    dict(READ_COMICBOX_DICT.items()), sort_keys=True, indent=2
)
WRITE_COMICBOX_STR = json.dumps(
    dict(WRITE_COMICBOX_DICT.items()), sort_keys=True, indent=2
)

COMICBOX_TESTER = TestParser(
    ComicboxJsonTransform,
    FN,
    READ_METADATA,
    READ_COMICBOX_DICT,
    READ_COMICBOX_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_COMICBOX_DICT,
    WRITE_COMICBOX_STR,
)


def test_comicbox_from_metadata():
    """Test assign metadata."""
    COMICBOX_TESTER.test_from_metadata()


def test_comicbox_from_dict():
    """Test native dict import from comicbox.schemas."""
    COMICBOX_TESTER.test_from_dict()


def test_comicbox_from_string():
    """Test metadata import from string."""
    COMICBOX_TESTER.test_from_string()


def test_comicbox_from_file():
    """Test metadata import from file."""
    COMICBOX_TESTER.test_from_file()


def test_comicbox_to_dict():
    """Test metadata export to dict."""
    COMICBOX_TESTER.test_to_dict()


def test_comicbox_to_string():
    """Test metadata export to string."""
    COMICBOX_TESTER.test_to_string()


def test_comicbox_to_file():
    """Test metadata export to file."""
    COMICBOX_TESTER.test_to_file(export_fn="comicbox-write.json")


def test_comicbox_read():
    """Test read from file."""
    COMICBOX_TESTER.test_md_read(page_count=36)


def test_comicbox_write():
    """Test write to file."""
    COMICBOX_TESTER.test_md_write(page_count=36)
