"""Test CBI module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import simplejson as json

from comicbox.fields.enum_fields import PageTypeEnum, ReadingDirectionEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.comicbox.json_schema import ComicboxJsonSchema
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
            "identifier_primary_source": {
                "id_source": "comicvine",
                "url": "https://comicvine.gamespot.com/",
            },
            "identifiers": {
                "comicvine": {
                    "id_key": "145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "summary": "A long example description",
            "bookmark": 12,
            "original_format": "Comic",
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
                12: {"bookmark": "true", "size": 445302},
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
TEST_LAST_MODIFIED = "1970-1-1"
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
            "bookmark": 12,
            "pages": {
                "00": {"page_type": "FrontCover", "size": 429985},
                "01": {"size": 332936},
                "02": {"size": 458657},
                "03": {"size": 450456},
                "04": {"size": 436648},
                "05": {"size": 443725},
                "06": {"size": 469526},
                "07": {"size": 429811},
                "08": {"size": 445513},
                "09": {"size": 446292},
                "10": {"size": 458589},
                "11": {"size": 417623},
                "12": {"bookmark": "true", "size": 445302},
                "13": {"size": 413271},
                "14": {"size": 434201},
                "15": {"size": 439049},
                "16": {"size": 485957},
                "17": {"size": 388379},
                "18": {"size": 368138},
                "19": {"size": 427874},
                "20": {"size": 422522},
                "21": {"size": 442529},
                "22": {"size": 423785},
                "23": {"size": 427980},
                "24": {"size": 445631},
                "25": {"size": 413615},
                "26": {"size": 417605},
                "27": {"size": 439120},
                "28": {"size": 451598},
                "29": {"size": 451550},
                "30": {"size": 438346},
                "31": {"size": 454914},
                "32": {"size": 428461},
                "33": {"size": 438091},
                "34": {"size": 353013},
                "35": {"size": 340840},
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
            "identifier_primary_source": {
                "id_source": "comicvine",
                "url": "https://comicvine.gamespot.com/",
            },
            "identifiers": {
                "comicvine": {
                    "id_key": "145269",
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
READ_MULTI_STR = json.dumps(dict(READ_MULTI_DICT), sort_keys=True, indent=2)
WRITE_MULTI_STR = json.dumps(dict(WRITE_MULTI_DICT), sort_keys=True, indent=2)

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


def test_multi_from_metadata():
    """Test assign metadata."""
    MULTI_TESTER.test_from_metadata()


def test_multi_to_dict():
    """Test metadata export to dict."""
    MULTI_TESTER.test_to_dict()


def test_multi_read():
    """Test read from file."""
    MULTI_TESTER.test_md_read(ignore_pages=True)


def test_multi_write():
    """Test write to file."""
    MULTI_TESTER.test_md_write(ignore_pages=True)
