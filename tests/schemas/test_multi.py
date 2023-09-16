"""Test CBI module."""
from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import simplejson as json

from comicbox.fields.enum import ReadingDirectionEnum
from comicbox.schemas.json import ComicboxJsonSchema
from tests.const import (
    CBZ_MULTI_FN,
    TEST_DATETIME,
    TEST_DTTM_STR,
    TEST_READ_NOTES,
)
from tests.util import TestParser, create_write_dict, create_write_metadata

READ_CONFIG = Namespace(comicbox=Namespace())
WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=("cix", "cbi", "comet", "fn", "cli", "ct", "cb"))
)
READ_METADATA = MappingProxyType(
    {
        "series": "Captain Science COMET",
        "issue": "001",
        "issue_number": Decimal(1),
        "issue_count": 77,
        "imprint": "CLIImprint",
        "publisher": "Youthful Adventure Stories COMICTAGGER",
        "month": 11,
        "year": 591,
        "genres": {"Science Fiction", "Comic Info Genre", "comicbox Genre"},
        "volume": 999,
        "contributors": {
            "penciller": {"Wally Wood CBI"},
            "writer": {"Joe Orlando CBI"},
        },
        "characters": {"Captain Science", "Gordon Dane", "COMET"},
        "language": "fr",
        "country": "US",
        "title": "The Beginning CBI",
        "page_count": 0,
        "day": 1,
        "story_arcs": {
            "e": 1,
            "f": 3,
            "g": 5,
            "h": 7,
            "i": 11,
            "j": 13,
            "Captain Arc": 4,
            "Other Arc": 2,
        },
        "tags": {"a", "b", "c"},
        "date": date(1950, 12, 1),
        "reading_direction": ReadingDirectionEnum.LTR,
        "price": Decimal("0.10"),
        "ext": "cbz",
        "notes": TEST_READ_NOTES,
        "age_rating": "Teen",
        "cover_image": "CaptainScience#1_01.jpg",
        "identifiers": {"comicvine": "145269"},
        "summary": "A long example description",
        "last_mark": 12,
        "remainders": ["multi"],
        "original_format": "Comic",
        "web": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
        "alternate_issue": "Captain Science",
        "rights": "Copyright (c) 1950 Bell Features",
        "updated_at": TEST_DATETIME,
        "tagger": "comicbox dev",
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
TEST_LAST_MODIFIED = "1970-1-1"
READ_MULTI_DICT = MappingProxyType(
    {
        "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.schema.json",
        "appID": "comicbox/dev",
        ComicboxJsonSchema.ROOT_TAG: {
            "country": "United States",
            "contributors": {
                "penciller": ["Wally Wood CBI"],
                "writer": ["Joe Orlando CBI"],
            },
            "characters": ["COMET", "Captain Science", "Gordon Dane"],
            "genres": [
                "Comic Info Genre",
                "Science Fiction",
                "comicbox Genre",
            ],
            "age_rating": "Teen",
            "issue": "001",
            "notes": TEST_READ_NOTES,
            "issue_number": Decimal(1),
            "issue_count": 77,
            "language": "French",
            "page_count": 0,
            "month": 11,
            "year": 591,
            "publisher": "Youthful Adventure Stories COMICTAGGER",
            "imprint": "CLIImprint",
            "series": "Captain Science COMET",
            "title": "The Beginning CBI",
            "volume": 999,
            "day": 1,
            "tags": ["a", "b", "c"],
            "story_arcs": {
                "e": 1,
                "f": 3,
                "g": 5,
                "h": 7,
                "i": 11,
                "j": 13,
                "Captain Arc": 4,
                "Other Arc": 2,
            },
            "date": "1950-12-01",
            "reading_direction": ReadingDirectionEnum.LTR.value,
            "price": Decimal("0.10"),
            "ext": "cbz",
            "cover_image": "CaptainScience#1_01.jpg",
            "identifiers": {"comicvine": "145269"},
            "summary": "A long example description",
            "last_mark": 12,
            "remainders": ["multi"],
            "original_format": "Comic",
            "web": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
            "alternate_issue": "Captain Science",
            "rights": "Copyright (c) 1950 Bell Features",
            "updated_at": TEST_DTTM_STR,
            "tagger": "comicbox dev",
        },
    }
)
WRITE_MULTI_DICT = create_write_dict(READ_MULTI_DICT, ComicboxJsonSchema, "notes")
READ_MULTI_STR = json.dumps(dict(READ_MULTI_DICT), sort_keys=True, indent=2)
WRITE_MULTI_STR = json.dumps(dict(WRITE_MULTI_DICT), sort_keys=True, indent=2)

MULTI_TESTER = TestParser(
    ComicboxJsonSchema,
    CBZ_MULTI_FN,
    READ_METADATA,
    READ_MULTI_DICT,
    READ_MULTI_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_MULTI_DICT,
    WRITE_MULTI_STR,
)


def test_multi_from_metadata():
    """Test assign metadata."""
    MULTI_TESTER.test_from_metadata()


def test_multi_to_dict():
    """Test metadata export to dict."""
    MULTI_TESTER.test_to_dict()


def test_multi_read():
    """Test read from file."""
    MULTI_TESTER.test_md_read()


def test_multi_write():
    """Test write to file."""
    MULTI_TESTER.test_md_write()
