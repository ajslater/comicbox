"""Test CBI module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

from comicbox.config import get_config
from comicbox.enums.comicbox import ReadingDirectionEnum
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.json_schemas import JsonRenderModule
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.json_schema import ComicboxJsonSchema
from tests.const import (
    CBZ_MULTI_FN,
    TEST_DATETIME,
    TEST_DTTM_STR,
    TEST_READ_NOTES,
)
from tests.util import TestParser, create_write_dict, create_write_metadata

READ_CONFIG = get_config(Namespace(comicbox=Namespace()))
WRITE_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            write=Namespace(formats=("cix", "cbi", "comet", "fn", "cli", "cb"))
        )
    )
)
READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {
                "Joe Orlando CBI": {"roles": {"Writer": {}}},
                "Wally Wood CBI": {"roles": {"Penciller": {}}},
            },
            "series": {"name": "Captain Science COMET"},
            "issue": {
                "name": "001",
                "number": Decimal(1),
            },
            "imprint": {"name": "CLIImprint"},
            "publisher": {"name": "Youthful Adventure Stories"},
            "date": {
                "cover_date": date(591, 11, 1),
                "day": 1,
                "month": 11,
                "year": 591,
            },
            "characters": {
                "Captain Science": {},
                "COMET": {},
                "Gordon Dane": {},
            },
            "genres": {
                "Science Fiction": {},
                "Comic Info Genre": {},
                "comicbox Genre": {},
            },
            "volume": {"number": 999, "issue_count": 77},
            "language": "en",
            "country": "US",
            "page_count": 0,
            "arcs": {
                "e": {"number": 1},
                "f": {"number": 3},
                "g": {"number": 5},
                "h": {"number": 7},
                "i": {"number": 11},
                "j": {"number": 13},
                "Captain Arc": {"number": 4},
                "Other Arc": {"number": 2},
            },
            "tags": {"a": {}, "b": {}, "c": {}},
            "reading_direction": ReadingDirectionEnum.LTR,
            "prices": {"": Decimal("0.10")},
            "ext": "cbz",
            "notes": TEST_READ_NOTES,
            "age_rating": "Teen",
            "cover_image": "CaptainScience#1_01.jpg",
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "summary": "A long example description",
            "bookmark": 4,
            "original_format": "Comic",
            "pages": {
                0: {"page_type": ComicInfoPageTypeEnum.FRONT_COVER, "size": 4542},
                1: {"size": 4065},
                2: {"size": 4081},
                3: {"size": 4157},
                4: {"bookmark": "true", "size": 4108},
            },
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ],
            "rights": "Copyright (c) 1950 Bell Features",
            "stories": {
                "The Beginning COMET": {},
            },
            "title": "The Beginning COMET",
            "updated_at": TEST_DATETIME,
            "tagger": "comicbox dev",
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_MULTI_DICT = MappingProxyType(
    {
        "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json",
        "appID": "comicbox dev",
        ComicboxJsonSchema.ROOT_TAG: {
            "country": "US",
            "credits": {
                "Joe Orlando CBI": {"roles": {"Writer": {}}},
                "Wally Wood CBI": {"roles": {"Penciller": {}}},
            },
            "characters": {
                "Captain Science": {},
                "COMET": {},
                "Gordon Dane": {},
            },
            "date": {
                "cover_date": "0591-11-01",
                "day": 1,
                "month": 11,
                "year": 591,
            },
            "genres": {
                "Science Fiction": {},
                "Comic Info Genre": {},
                "comicbox Genre": {},
            },
            "age_rating": "Teen",
            "issue": {
                "name": "001",
                "number": Decimal(1),
            },
            "notes": TEST_READ_NOTES,
            "language": "en",
            "page_count": 0,
            "bookmark": 4,
            "pages": {
                "0": {"page_type": "FrontCover", "size": 4542},
                "1": {"size": 4065},
                "2": {"size": 4081},
                "3": {"size": 4157},
                "4": {"bookmark": "true", "size": 4108},
            },
            "publisher": {"name": "Youthful Adventure Stories"},
            "imprint": {"name": "CLIImprint"},
            "series": {"name": "Captain Science COMET"},
            "volume": {"number": 999, "issue_count": 77},
            "tags": {"a": {}, "b": {}, "c": {}},
            "arcs": {
                "e": {"number": 1},
                "f": {"number": 3},
                "g": {"number": 5},
                "h": {"number": 7},
                "i": {"number": 11},
                "j": {"number": 13},
                "Captain Arc": {"number": 4},
                "Other Arc": {"number": 2},
            },
            "reading_direction": ReadingDirectionEnum.LTR.value,
            "prices": {"": Decimal("0.10")},
            "ext": "cbz",
            "cover_image": "CaptainScience#1_01.jpg",
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "summary": "A long example description",
            "stories": {
                "The Beginning COMET": {},
            },
            "title": "The Beginning COMET",
            "original_format": "Comic",
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ],
            "rights": "Copyright (c) 1950 Bell Features",
            "updated_at": TEST_DTTM_STR,
            "tagger": "comicbox dev",
        },
    }
)
WRITE_MULTI_DICT = create_write_dict(READ_MULTI_DICT, ComicboxJsonSchema, "notes")
READ_MULTI_STR = JsonRenderModule.dumps(READ_MULTI_DICT)
WRITE_MULTI_STR = JsonRenderModule.dumps(WRITE_MULTI_DICT)

MULTI_TESTER = TestParser(
    MetadataFormats.COMICBOX_JSON,
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


def test_multi_from_metadata() -> None:
    """Test assign metadata."""
    MULTI_TESTER.test_from_metadata()


def test_multi_to_dict() -> None:
    """Test metadata export to dict."""
    MULTI_TESTER.test_to_dict()


def test_multi_read() -> None:
    """Test read from file."""
    MULTI_TESTER.test_md_read(ignore_pages=True, page_count=5)


def test_multi_write() -> None:
    """Test write to file."""
    MULTI_TESTER.test_md_write(ignore_pages=True)
