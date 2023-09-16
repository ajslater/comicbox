"""Test CIX module."""
from argparse import Namespace
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.fields.enum import ReadingDirectionEnum
from comicbox.schemas.comet import CoMetSchema
from tests.util import (
    TestParser,
)

FN = "Captain Science #001-comet.cbz"
READ_CONFIG = Namespace(comicbox=Namespace(read=["comet"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["comet"], read=["comet"]))

METADATA = MappingProxyType(
    {
        "age_rating": "Teen",
        "alternate_issue": "Captain Science",
        "cover_image": "CaptainScience#1_01.jpg",
        "characters": {"Captain Science", "Gordon Dane"},
        "contributors": {
            "writer": {"Joe Orlando"},
            "penciller": {"Wally Wood"},
        },
        "date": datetime.strptime("1950-12-01", "%Y-%m-%d").date(),  # noqa: DTZ007
        "genres": {"Science Fiction"},
        "identifiers": {"comicvine": "145269"},
        "issue": "1",
        "issue_number": Decimal("1"),
        "language": "en",
        "last_mark": 12,
        "publisher": "Bell Features",
        "original_format": "Comic",
        "page_count": 36,
        "price": Decimal(0.10).quantize(Decimal("0.01")),
        "reading_direction": ReadingDirectionEnum.LTR,
        "rights": "Copyright (c) 1950 Bell Features",
        "title": "The Beginning",
        "series": "Captain Science",
        "summary": "A long example description",
        "volume": 1,
        "web": "https://comicvine.gamespot.com/c/4000-145269/",
    }
)
COMET_DICT = MappingProxyType(
    {
        CoMetSchema.ROOT_TAG: {
            "@xmlns:comet": "http://www.denvog.com/comet/",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "http://www.denvog.com/comet/comet.xsd",
            "character": ["Captain Science", "Gordon Dane"],
            "coverImage": "CaptainScience#1_01.jpg",
            "date": "1950-12-01",
            "description": "A long example description",
            "format": "Comic",
            "genre": ["Science Fiction"],
            "identifier": "urn:comicvine:145269",
            "isVersionOf": "Captain Science",
            "issue": "1",
            "language": "English",
            "lastMark": 12,
            "pages": 36,
            "penciller": ["Wally Wood"],
            "price": Decimal("0.10").quantize(Decimal("0.01")),
            "publisher": "Bell Features",
            "rating": "Teen",
            "readingDirection": "ltr",
            "rights": "Copyright (c) 1950 Bell Features",
            "series": "Captain Science",
            "title": "The Beginning",
            "volume": 1,
            "writer": ["Joe Orlando"],
        }
    }
)
COMET_STR = xmltodict.unparse(COMET_DICT, pretty=True, short_empty_elements=True)

COMET_TESTER = TestParser(
    CoMetSchema,
    FN,
    METADATA,
    COMET_DICT,
    COMET_STR,
    READ_CONFIG,
    WRITE_CONFIG,
)


def test_comet_from_metadata():
    """Test metadata import from comicbox.schemas."""
    COMET_TESTER.test_from_metadata()


def test_comet_from_dict():
    """Test native dict import from comicbox.schemas."""
    COMET_TESTER.test_from_dict()


def test_comet_from_string():
    """Test metadata import from string."""
    COMET_TESTER.test_from_string()


def test_comet_from_file():
    """Test metadata import from file."""
    COMET_TESTER.test_from_file()


def test_comet_to_dict():
    """Test metadata export to dict."""
    COMET_TESTER.test_to_dict()


def test_comet_to_string():
    """Test metadata export to string."""
    COMET_TESTER.to_string()


def test_comet_to_file():
    """Test metadata export to file."""
    COMET_TESTER.test_to_file(export_fn="comet-write.xml")


def test_comet_read():
    """Read comet metadata."""
    COMET_TESTER.test_md_read()


def test_comet_write():
    """Write comet metadata."""
    COMET_TESTER.test_md_write()
