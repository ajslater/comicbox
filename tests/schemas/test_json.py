"""Test CBI module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import simplejson as json

from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.comicbox.json_schema import ComicboxJsonSchema
from tests.const import TEST_DATETIME, TEST_DTTM_STR, TEST_READ_NOTES
from tests.util import TestParser, create_write_dict, create_write_metadata

FN = Path("comicbox.cbz")
READ_CONFIG = Namespace(comicbox=Namespace(read=["json", "fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["json"], read=["json"]))
READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "country": "US",
            "series": {"name": "Captain Science"},
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
            "publisher": {"name": "Youthful Adventure Stories"},
            "date": {
                "cover_date": date(1950, 11, 1),
                "month": 11,
                "year": 1950,
                "day": 1,
            },
            "genres": {"Science Fiction": {}},
            "volume": {
                "number": 1950,
                "issue_count": 7,
            },
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "language": "en",
            "stories": {"The Beginning": {}},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": TEST_DATETIME,
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
        },
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_COMICBOX_DICT = MappingProxyType(
    {
        "appID": "comicbox dev",
        ComicboxJsonSchema.ROOT_TAG: {
            "country": "US",
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "date": {
                "cover_date": "1950-11-01",
                "day": 1,
                "month": 11,
                "year": 1950,
            },
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
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science"},
            "tagger": "comicbox dev",
            "stories": {"The Beginning": {}},
            "title": "The Beginning",
            "updated_at": TEST_DTTM_STR,
            "volume": {
                "number": 1950,
                "issue_count": 7,
            },
            "pages": {
                "00": {
                    "page_type": PageTypeEnum.FRONT_COVER.value,
                    "size": 429985,
                },
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
                "12": {"size": 445302},
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
        },
        "schema": "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/comicbox-v2.0.schema.json",
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
    MetadataFormats.COMICBOX_JSON,
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
    COMICBOX_TESTER.test_md_read(page_count=0)


def test_comicbox_write():
    """Test write to file."""
    COMICBOX_TESTER.test_md_write(page_count=0)
