"""Test CBI module."""

from argparse import Namespace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import simplejson as json

from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.comictagger import ComictaggerSchema
from comicbox.transforms.comictagger import ComictaggerTransform
from tests.const import TEST_DATETIME, TEST_READ_NOTES
from tests.util import TestParser, create_write_dict, create_write_metadata

FN = Path("comictagger.cbz")
READ_CONFIG = Namespace(comicbox=Namespace(read=["ct"], compute_pages=False))
WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=["ct"], read=["ct"], compute_pages=False)
)
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
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
            "notes": TEST_READ_NOTES,
            "year": 1950,
            "day": 1,
            "genres": {"Science Fiction"},
            "volume": {"name": 1950, "issue_count": 7},
            "contributors": {
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "language": "en",
            "country": "US",
            "title": "The Beginning",
            "page_count": 0,
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_CT_DICT = MappingProxyType(
    {
        ComictaggerSchema.ROOT_TAGS[0]: {
            "country": "US",
            "credits": [
                {"person": "Wally Wood", "role": "Penciller"},
                {
                    "person": "Joe Orlando",
                    "role": "Writer",
                },
            ],
            "day": 1,
            "genres": ["Science Fiction"],
            "issue": "1",
            "issue_count": 7,
            "issue_id": "4000-145269",
            "identifier": "urn:comicvine:4000-145269",
            "language": "en",
            "month": 11,
            "notes": TEST_READ_NOTES,
            "page_count": 0,
            "publisher": "Youthful Adventure Stories",
            "series": "Captain Science",
            "tag_origin": {"name": "comicvine"},
            "title": "The Beginning",
            "volume": 1950,
            "year": 1950,
            "web_link": "https://comicvine.gamespot.com/c/4000-145269/",
        },
    }
)
WRITE_CT_DICT = create_write_dict(READ_CT_DICT, ComictaggerSchema, "notes")
READ_CT_STR = json.dumps(dict(READ_CT_DICT.items()), sort_keys=True, indent=2)
WRITE_CT_STR = json.dumps(dict(WRITE_CT_DICT.items()), sort_keys=True, indent=2)


CT_TESTER = TestParser(
    ComictaggerTransform,
    FN,
    READ_METADATA,
    READ_CT_DICT,
    READ_CT_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_CT_DICT,
    WRITE_CT_STR,
)


def test_ct_from_metadata():
    """Test assign metadata."""
    CT_TESTER.test_from_metadata()


def test_ct_from_dict():
    """Test native dict import from comicbox.schemas."""
    CT_TESTER.test_from_dict()


def test_ct_from_string():
    """Test metadata import from string."""
    CT_TESTER.test_from_string()


def test_ct_from_file():
    """Test metadata import from file."""
    CT_TESTER.test_from_file()


def test_ct_to_dict():
    """Test metadata export to dict."""
    CT_TESTER.test_to_dict()


def test_ct_to_string():
    """Test metadata export to string."""
    CT_TESTER.test_to_string()


def test_ct_to_file():
    """Test metadata export to file."""
    CT_TESTER.test_to_file(export_fn="comictagger-write.json")


def test_ct_read():
    """Test read from file."""
    CT_TESTER.test_md_read()


def test_ct_write():
    """Test write to file."""
    CT_TESTER.test_md_write()
