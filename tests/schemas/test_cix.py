"""Test CIX module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.comicinfo import ComicInfoSchema
from comicbox.schemas.xml_schemas import XML_UNPARSE_ARGS
from tests.const import CIX_CBZ_FN, TEST_DATETIME, TEST_READ_NOTES
from tests.util import (
    TestParser,
    create_write_dict,
    create_write_metadata,
)

WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cix"], read=["cix"]))
READ_CONFIG = Namespace(comicbox=Namespace(read=["cix", "fn"]))
READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "age_rating": "Teen",
            "arcs": {
                "Captain Arc": {"number": 4},
                "Other Arc": {"number": 2},
            },
            "date": {
                "cover_date": date(1950, 11, 1),
                "year": 1950,
                "month": 11,
                "day": 1,
            },
            "series": {"name": "Captain Science"},
            "issue": {
                "name": "1",
                "number": Decimal("1"),
            },
            "publisher": {"name": "Youthful Adventure Stories"},
            "volume": {"number": 1950, "issue_count": 7},
            "language": "en",
            "notes": TEST_READ_NOTES,
            "characters": {
                "Captain Science": {},
                "Gordon Dane": {},
            },
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
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
            "page_count": 36,
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ],
            "stories": {"The Beginning": {}, "The End": {}},
            "tagger": "comicbox dev",
            "title": "The Beginning; The End",
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)

READ_CIX_DICT = MappingProxyType(
    {
        ComicInfoSchema.ROOT_TAG: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": (
                "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1 "
                "https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd"
            ),
            "Title": "The Beginning; The End",
            "Series": "Captain Science",
            "Number": "1",
            "Count": 7,
            "Volume": 1950,
            "AlternateSeries": "Captain Science Alternate",
            "AlternateNumber": "001",
            "Notes": TEST_READ_NOTES,
            "Year": 1950,
            "Month": 11,
            "Day": 1,
            "Writer": "Joe Orlando",
            "Penciller": "Wally Wood",
            "Inker": "Wally Wood",
            "Publisher": "Youthful Adventure Stories",
            "Genre": "Science Fiction",
            "Web": "https://comicvine.gamespot.com/c/4000-145269/",
            "PageCount": 36,
            "LanguageISO": "en",
            "Characters": "Captain Science,Gordon Dane",
            "StoryArc": "Captain Arc,Other Arc",
            "StoryArcNumber": "4,2",
            "AgeRating": "Teen",
            "Pages": {
                "Page": [
                    {"@Image": 0, "@ImageSize": 429985, "@Type": "FrontCover"},
                    {"@Image": 1, "@ImageSize": 332936},
                    {"@Image": 2, "@ImageSize": 458657},
                    {"@Image": 3, "@ImageSize": 450456},
                    {"@Image": 4, "@ImageSize": 436648},
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
                    {"@Image": 25, "@ImageSize": 413615},
                    {"@Image": 26, "@ImageSize": 417605},
                    {"@Image": 27, "@ImageSize": 439120},
                    {"@Image": 28, "@ImageSize": 451598},
                    {"@Image": 29, "@ImageSize": 451550},
                    {"@Image": 30, "@ImageSize": 438346},
                    {"@Image": 31, "@ImageSize": 454914},
                    {"@Image": 32, "@ImageSize": 428461},
                    {"@Image": 33, "@ImageSize": 438091},
                    {"@Image": 34, "@ImageSize": 353013},
                    {"@Image": 35, "@ImageSize": 340840},
                ]
            },
            "GTIN": "urn:comicvine:145269",
        }
    }
)
WRITE_CIX_DICT = create_write_dict(READ_CIX_DICT, ComicInfoSchema, "Notes")
READ_CIX_STR = xmltodict.unparse(READ_CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]
WRITE_CIX_STR = xmltodict.unparse(WRITE_CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]

CIX_TESTER = TestParser(
    MetadataFormats.COMIC_INFO,
    CIX_CBZ_FN,
    READ_METADATA,
    READ_CIX_DICT,
    READ_CIX_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_CIX_DICT,
    WRITE_CIX_STR,
)


def test_cix_from_metadata():
    """Test metadata import from comicbox.schemas."""
    CIX_TESTER.test_from_metadata()


def test_cix_from_dict():
    """Test native dict import."""
    CIX_TESTER.test_from_dict()


def test_cix_from_string():
    """Test metadata import from string."""
    CIX_TESTER.test_from_string()


def test_cix_from_file():
    """Test metadata import from file."""
    CIX_TESTER.test_from_file(page_count=0)


def test_cix_to_dict():
    """Test metadata export to dict."""
    CIX_TESTER.test_to_dict()


def test_cix_to_string():
    """Test metadata export to string."""
    test_str = CIX_TESTER.to_string()
    CIX_TESTER.compare_string(test_str)


def test_cix_to_file():
    """Test metadata export to file."""
    CIX_TESTER.test_to_file(export_fn="comicinfo-write.xml")


def test_cix_read():
    """Read RAR with CIX."""
    CIX_TESTER.test_md_read()


def test_cix_write():
    """Write cbz with CIX."""
    CIX_TESTER.test_md_write(ignore_pages=True, page_count=0)
