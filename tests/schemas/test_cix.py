"""Test CIX module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.config import get_config
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.xml_schemas import XML_UNPARSE_ARGS
from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from tests.const import CIX_CBZ_FN, TEST_DATETIME, TEST_READ_NOTES
from tests.util import (
    TestParser,
    create_write_dict,
    create_write_metadata,
)

WRITE_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            compute=Namespace(pages=True),
            read=Namespace(formats=["cix"]),
            write=Namespace(formats=["cix"]),
        )
    )
)
READ_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            read=Namespace(formats=["cix"]),
            compute=Namespace(pages=True, page_count=False),
        )
    )
)
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
                "number": Decimal(1),
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
                0: {"page_type": ComicInfoPageTypeEnum.FRONT_COVER, "size": 4542},
                1: {"size": 4065},
                2: {"size": 4081},
                3: {"size": 4157},
                4: {"size": 4108},
            },
            "page_count": 5,
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
            "PageCount": 5,
            "LanguageISO": "en",
            "Characters": "Captain Science,Gordon Dane",
            "StoryArc": "Captain Arc,Other Arc",
            "StoryArcNumber": "4,2",
            "AgeRating": "Teen",
            "Pages": {
                "Page": [
                    {"@Image": 0, "@ImageSize": 4542, "@Type": "FrontCover"},
                    {"@Image": 1, "@ImageSize": 4065},
                    {"@Image": 2, "@ImageSize": 4081},
                    {"@Image": 3, "@ImageSize": 4157},
                    {"@Image": 4, "@ImageSize": 4108},
                ]
            },
            "GTIN": "urn:comicvine:issue:145269",
        }
    }
)
WRITE_CIX_DICT = create_write_dict(READ_CIX_DICT, ComicInfoSchema, "Notes")
READ_CIX_STR = xmltodict.unparse(READ_CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue],  # ty: ignore[no-matching-overload]
WRITE_CIX_STR = xmltodict.unparse(WRITE_CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue],  # ty: ignore[no-matching-overload]

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


def test_cix_from_metadata() -> None:
    """Test metadata import from comicbox.formats.base.schemas."""
    CIX_TESTER.test_from_metadata()


def test_cix_from_dict() -> None:
    """Test native dict import."""
    CIX_TESTER.test_from_dict()


def test_cix_from_string() -> None:
    """Test metadata import from string."""
    CIX_TESTER.test_from_string()


def test_cix_from_file() -> None:
    """Test metadata import from file."""
    CIX_TESTER.test_from_file(page_count=0)


def test_cix_to_dict() -> None:
    """Test metadata export to dict."""
    CIX_TESTER.test_to_dict()


def test_cix_to_string() -> None:
    """Test metadata export to string."""
    test_str = CIX_TESTER.to_string()
    CIX_TESTER.compare_string(test_str)


def test_cix_to_file() -> None:
    """Test metadata export to file."""
    CIX_TESTER.test_to_file(export_fn="comicinfo-write.xml")


def test_cix_read() -> None:
    """Read RAR with CIX."""
    CIX_TESTER.test_md_read(page_count=0)


def test_cix_write() -> None:
    """Write cbz with CIX."""
    CIX_TESTER.test_md_write(ignore_pages=True, page_count=0)
