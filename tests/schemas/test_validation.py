"""Test CIX module."""
from argparse import Namespace
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.fields.enum import PageTypeEnum
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.comicinfo import ComicInfoSchema
from comicbox.transforms.comicinfo import ComicInfoTransform
from tests.const import TEST_DATETIME, TEST_READ_NOTES
from tests.util import (
    TestParser,
    create_write_dict,
    create_write_metadata,
)

EXPORT_FN = "comicinfo-validation.xml"
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cix"], read=["cix"]))
READ_CONFIG = Namespace(comicbox=Namespace(read=["cix"]))
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "series": {"name": "2"},  # "Captain Science",
            "issue": "1",
            "issue_number": Decimal("1"),
            "publisher": "Youthful Adventure Stories",
            "year": 1950,
            "month": 11,
            "day": 1,
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "volume": {
                "number": 1950,
                "issue_count": 7,
            },
            "language": "en",
            "notes": TEST_READ_NOTES,
            "characters": {
                "Captain Science",
                "Gordon Dane",
            },
            "contributors": {
                "inker": {"Wally Wood"},
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "genres": {"Science Fiction"},
            "pages": [
                {"index": 0, "size": 429985, "page_type": PageTypeEnum.FRONT_COVER},
                {"index": 1, "size": 332936},
                {"index": 2, "size": 458657},
                {"index": 3, "size": 450456},
                {"index": 4},  # , "size": 436648},
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
                {"index": 25},  # , "size": 413615},
                {"index": 26},  # , "size": 417605},
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
            "page_count": 36,
            "story_arcs": {
                "Captain Arc": 4,
                "Other Arc": 2,
            },
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
            # "title": "The Beginning",
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_CIX_DICT = MappingProxyType(
    {
        ComicInfoSchema.ROOT_TAGS[0]: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1",
            "Characters": "Captain Science,Gordon Dane",
            "Count": 7,
            "Day": -1,
            "Genre": "Science Fiction",
            "Inker": "Wally Wood",
            "LanguageISO": "English",
            "Month": 11,
            "Notes": TEST_READ_NOTES,
            "Number": "1",
            "PageCount": frozenset({36}),
            "Pages": {
                "Page": [
                    {"@Image": 0, "@ImageSize": 429985, "@Type": "FrontCover"},
                    {"@Image": 1, "@ImageSize": 332936, "@Type": "FOO"},
                    {"@Image": 2, "@ImageSize": 458657, "@EXTRA": 0},
                    {"@Image": 3, "@ImageSize": 450456},
                    {"@Image": 4, "@ImageSize": "boochalla"},
                    {"@Image": 5, "@ImageSize": 443725},
                    {"@Image": 6, "@ImageSize": 469526},
                    {"@Image": 7, "@ImageSize": 429811},
                    {"@Image": 8, "@ImageSize": 445513},
                    {"@Image": 9, "@ImageSize": 446292},
                    {"@Image": 10, "@ImageSize": 458589},
                    {"@Image": 11, "@ImageSize": 417623},
                    {"@Image": 12, "@ImageSize": 445302},
                    {"@Image": 13, "@ImageSize": 413271},
                    {"@Image": 14, "@ImageSize": 434201},
                    {"@Image": 15, "@ImageSize": 439049},
                    {"@Image": 16, "@ImageSize": 485957},
                    {"@Image": 17, "@ImageSize": 388379},
                    {"@Image": 18, "@ImageSize": 368138},
                    {"@Image": 19, "@ImageSize": 427874},
                    {"@Image": 20, "@ImageSize": 422522},
                    {"@Image": 21, "@ImageSize": 442529},
                    {"@Image": 22, "@ImageSize": 423785},
                    {"@Image": 23, "@ImageSize": 427980},
                    {"@Image": 24, "@ImageSize": 445631},
                    {"@Image": 25},  # , "@ImageSize": [413615]},
                    {"@Image": 26, "@ImageSize": {"a": "b"}},
                    {"@Image": 27, "@ImageSize": "439120"},
                    {"@Image": "28", "@ImageSize": 451598},
                    {"@Image": 29, "@ImageSize": 451550},
                    {"@Image": 30, "@ImageSize": 438346},
                    {"@Image": 31, "@ImageSize": 454914},
                    {"@Image": 32, "@ImageSize": 428461},
                    {"@Image": 33, "@ImageSize": 438091},
                    {"@Image": 34, "@ImageSize": 353013},
                    {"@Image": 35, "@ImageSize": 340840},
                ]
            },
            "Penciller": "Wally Wood",
            "Publisher": "Youthful Adventure Stories",
            "Series": Decimal("2"),
            "StoryArc": "Captain Arc,Other Arc",
            "StoryArcNumber": "4,2",
            "Title": None,  # "The Beginning",
            "Volume": [1950],
            "Web": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
            "Writer": "Joe Orlando",
            "Year": "1950",
        }
    }
)
WRITE_CIX_DICT = create_write_dict(READ_CIX_DICT, ComicInfoSchema, "Notes")
READ_CIX_STR = xmltodict.unparse(READ_CIX_DICT, pretty=True, short_empty_elements=True)
WRITE_CIX_STR = xmltodict.unparse(
    WRITE_CIX_DICT, pretty=True, short_empty_elements=True
)

CIX_TESTER = TestParser(
    ComicInfoTransform,
    "",
    READ_METADATA,
    READ_CIX_DICT,
    READ_CIX_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_CIX_DICT,
    WRITE_CIX_STR,
    export_fn=EXPORT_FN,
)


def test_cix_validation_from_metadata():
    """Test metadata import from comicbox.schemas."""
    CIX_TESTER.test_from_metadata()


# Don't test this, test from string & file instead.
# def test_cix_validation_from_dict():
#    """Test native dict import."""
#    CIX_TESTER.test_from_dict()


def test_cix_validation_from_string():
    """Test metadata import from string."""
    CIX_TESTER.test_from_string()


def test_cix_validation_from_file():
    """Test metadata import from file."""
    CIX_TESTER.test_from_file()
