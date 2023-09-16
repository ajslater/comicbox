"""Test CBI module."""
from argparse import Namespace
from decimal import Decimal
from types import MappingProxyType

import simplejson as json

from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from tests.const import CBI_CBR_FN, TEST_DTTM_STR
from tests.util import TestParser

READ_CONFIG = Namespace(comicbox=Namespace(read=["cbi"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cbi"], read=["cbi"]))
METADATA = MappingProxyType(
    {
        "series": "Captain Science",
        "issue": "1",
        "issue_number": Decimal(1),
        "issue_count": 7,
        "publisher": "Youthful Adventure Stories",
        "month": 11,
        "year": 1950,
        "genres": {"Science Fiction"},
        "volume": 1950,
        "contributors": {
            "penciller": {"Wally Wood"},
            "writer": {"Joe Orlando"},
        },
        "language": "en",
        "country": "US",
        "title": "The Beginning",
        "page_count": 36,
    }
)
CBI_DICT = MappingProxyType(
    {
        ComicBookInfoSchema.ROOT_TAG: {
            "country": "United States",
            "credits": [
                {"person": "Wally Wood", "role": "Penciller"},
                {"person": "Joe Orlando", "role": "Writer"},
            ],
            "genre": "Science Fiction",
            "issue": "1",
            "language": "English",
            "numberOfIssues": 7,
            "pages": 36,
            "publicationMonth": 11,
            "publicationYear": 1950,
            "publisher": "Youthful Adventure Stories",
            "series": "Captain Science",
            "title": "The Beginning",
            "volume": 1950,
        },
        "appID": "comicbox/dev",
        "lastModified": TEST_DTTM_STR,
        "schema": "https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki",
    }
)

CBI_STR = json.dumps(dict(CBI_DICT), sort_keys=True, indent=2)

CBI_TESTER = TestParser(
    ComicBookInfoSchema,
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
    CBI_TESTER.test_md_write()
