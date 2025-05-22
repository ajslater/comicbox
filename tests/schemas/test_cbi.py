"""Test CBI module."""

from argparse import Namespace
from decimal import Decimal
from types import MappingProxyType

import simplejson as json

from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from tests.const import CBI_CBR_FN, TEST_DATETIME, TEST_DTTM_STR
from tests.util import TestParser

READ_CONFIG = Namespace(comicbox=Namespace(read=["cbi", "fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cbi"], read=["cbi"]))
METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "country": "US",
            "genres": {"Science Fiction": {}},
            "issue": {
                "name": "1",
                "number": Decimal(1),
            },
            "language": "en",
            "date": {
                "year": 1950,
                "month": 11,
            },
            "page_count": 36,
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science", "volume_count": 1},
            "stories": {"The Beginning": {}},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": TEST_DATETIME,
            "volume": {
                "issue_count": 7,
                "number": 1950,
            },
        }
    }
)
CBI_DICT = MappingProxyType(
    {
        "appID": "comicbox dev",
        "lastModified": TEST_DTTM_STR,
        # ComicBookInfoSchema.ROOT_TAG: {
        ComicBookInfoSchema.ROOT_DATA_KEY: {
            "country": "United States",
            "credits": [
                {"person": "Joe Orlando", "role": "Writer"},
                {"person": "Wally Wood", "role": "Penciller"},
            ],
            "genre": "Science Fiction",
            "issue": 1,
            "language": "English",
            "numberOfIssues": 7,
            "numberOfVolumes": 1,
            "pages": 36,
            "publicationMonth": 11,
            "publicationYear": 1950,
            "publisher": "Youthful Adventure Stories",
            "series": "Captain Science",
            "title": "The Beginning",
            "volume": 1950,
        },
        "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/comic-book-info-v1.0.schema.json",
    }
)

CBI_STR = json.dumps(dict(CBI_DICT), sort_keys=False, indent=2)

CBI_TESTER = TestParser(
    MetadataFormats.COMIC_BOOK_INFO,
    CBI_CBR_FN,
    METADATA,
    CBI_DICT,
    CBI_STR,
    READ_CONFIG,
    WRITE_CONFIG,
)


def test_cbi_from_metadata():
    """Test assign metadata."""
    CBI_TESTER.test_from_metadata()


def test_cbi_from_dict():
    """Test native dict import from comicbox.schemas."""
    CBI_TESTER.test_from_dict()


def test_cbi_from_string():
    """Test metadata import from string."""
    CBI_TESTER.test_from_string()


def test_cbi_from_file():
    """Test metadata import from file."""
    CBI_TESTER.test_from_file()


def test_cbi_to_dict():
    """Test metadata export to dict."""
    CBI_TESTER.test_to_dict()


def test_cbi_to_string():
    """Test metadata export to string."""
    CBI_TESTER.test_to_string()


def test_cbi_to_file():
    """Test metadata export to file."""
    CBI_TESTER.test_to_file()


def test_cbi_read():
    """Test read from file."""
    CBI_TESTER.test_md_read()


def test_cbi_write():
    """Test write to file."""
    CBI_TESTER.test_md_write(page_count=0)
