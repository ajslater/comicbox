"""Test CIX module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.fields.enum_fields import ReadingDirectionEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comet import CoMetSchema
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.xml_schemas import XML_UNPARSE_ARGS
from tests.util import TestParser

FN = "Captain Science #001-comet.cbz"
READ_CONFIG = Namespace(comicbox=Namespace(read=["comet", "fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["comet"], read=["comet"]))

METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "age_rating": "Teen",
            "cover_image": "CaptainScience#1_01.jpg",
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "date": {
                "cover_date": date(1950, 12, 1),
                "day": 1,
                "month": 12,
                "year": 1950,
            },
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": {"name": "1", "number": Decimal("1")},
            "language": "en",
            "bookmark": 12,
            "publisher": {"name": "Bell Features"},
            "original_format": "Comic",
            "page_count": 36,
            "prices": {"": Decimal("0.10").quantize(Decimal("0.01"))},
            "reading_direction": ReadingDirectionEnum.LTR,
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ],
            "rights": "Copyright (c) 1950 Bell Features",
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "summary": "A long example description",
            "title": "The Beginning",
            "volume": {"number": 1},
        }
    }
)
COMET_DICT = MappingProxyType(
    {
        CoMetSchema.ROOT_TAG: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xmlns:comet": "http://www.denvog.com/comet/",
            "@xsi:schemaLocation": "http://www.denvog.com/comet/ https://github.com/ajslater/comicbox/blob/main/schemas/CoMet-v1.1.xsd",
            "character": ["Captain Science", "Gordon Dane"],
            "writer": ["Joe Orlando"],
            "coverImage": "CaptainScience#1_01.jpg",
            "date": "1950-12-01",
            "description": "A long example description",
            "format": "Comic",
            "genre": ["Science Fiction"],
            "identifier": "urn:comicvine:145269",
            "isVersionOf": "Captain Science Alternate #001",
            "issue": "1",
            "language": "en",
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
        }
    }
)
COMET_STR = xmltodict.unparse(COMET_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType,reportCallIssue]

COMET_TESTER = TestParser(
    MetadataFormats.COMET,
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
    COMET_TESTER.test_md_write(page_count=0)
