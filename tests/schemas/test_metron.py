"""Test METRON module."""

from argparse import Namespace
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.transforms.metroninfo import MetronInfoTransform
from tests.const import METRON_CBZ_FN, TEST_DATETIME
from tests.util import (
    TestParser,
    create_write_dict,
    create_write_metadata,
)

WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=["mi"], read=["mi"], compute_pages=False)
)
READ_CONFIG = Namespace(comicbox=Namespace(read=["mi"], compute_pages=False))
METRON_NOTES = (
    "Tagged with "
    "comicbox dev "
    "on "
    "1970-01-01T00:00:00 "
    "[Issue ID "
    "145269] "
    "urn:comicvine:4000-145269 "
    "urn:isbn:123-456789-0123 "
    "urn:upc:12345"
)
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "series": {"name": "Captain Science"},
            "issue": "1",
            "issue_number": Decimal("1"),
            "publisher": "Youthful Adventure Stories",
            "date": date(year=1950, month=11, day=1),
            "volume": {"name": 1950},
            "language": "en",
            "notes": METRON_NOTES,
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
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "upc": {"nss": "12345", "url": "https://barcodelookup.com/12345/"},
                "isbn": {
                    "nss": "123-456789-0123",
                    "url": "https://isbndb.com/book/123-456789-0123/",
                },
            },
            "page_count": 0,
            "stories": {"Captain Lost", "Science is Good"},
            "story_arcs": {
                "Captain Arc": 4,
                "Other Arc": 2,
            },
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ],
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA, notes=METRON_NOTES)


READ_METRON_DICT = MappingProxyType(
    {
        MetronInfoSchema.ROOT_TAGS[0]: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0",
            "Arcs": {
                "Arc": [
                    {"Name": "Captain Arc", "Number": 4},
                    {"Name": "Other Arc", "Number": 2},
                ]
            },
            "Characters": {
                "Character": [
                    {"#text": "Captain Science"},
                    {"#text": "Gordon Dane"},
                ]
            },
            "CoverDate": "1950-11-01",
            "Credits": {
                "Credit": [
                    {
                        "Creator": {"#text": "Joe Orlando"},
                        "Roles": {"Role": [{"#text": "Writer"}]},
                    },
                    {
                        "Creator": {"#text": "Wally Wood"},
                        "Roles": {"Role": [{"#text": "Inker"}, {"#text": "Penciller"}]},
                    },
                ]
            },
            "GTIN": {"ISBN": "123-456789-0123", "UPC": "12345"},
            "Genres": {"Genre": [{"#text": "Science Fiction"}]},
            "ID": {"@source": "Comic Vine"},
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Publisher": {"#text": "Youthful Adventure Stories"},
            "Reprints": {"Reprint": [{"#text": "Captain Science Alternate #001"}]},
            "Series": {
                "@lang": "en",
                "Name": "Captain Science",
                "Volume": 1950,
            },
            "Stories": {
                "Story": [{"#text": "Captain Lost"}, {"#text": "Science is Good"}]
            },
            "URL": "https://comicvine.gamespot.com/c/4000-145269/",
        }
    }
)
SIMPLE_READ_METRON_DICT = MappingProxyType(
    {
        MetronInfoSchema.ROOT_TAGS[0]: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0",
            "Arcs": {
                "Arc": [
                    {"Name": "Captain Arc", "Number": 4},
                    {"Name": "Other Arc", "Number": 2},
                ]
            },
            "Characters": {
                "Character": [
                    "Captain Science",
                    "Gordon Dane",
                ]
            },
            "CoverDate": "1950-11-01",
            "Credits": {
                "Credit": [
                    {
                        "Creator": "Joe Orlando",
                        "Roles": {"Role": ["Writer"]},
                    },
                    {
                        "Creator": "Wally Wood",
                        "Roles": {"Role": ["Inker", "Penciller"]},
                    },
                ]
            },
            "GTIN": {
                "ISBN": "123-456789-0123",
                "UPC": "12345",
            },
            "Genres": {"Genre": "Science Fiction"},
            "ID": {"@source": "Comic Vine"},
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Publisher": "Youthful Adventure Stories",
            "Reprints": {"Reprint": [{"#text": "Captain Science Alternate #001"}]},
            "Series": {
                "@lang": "en",
                "Name": "Captain Science",
                "Volume": 1950,
            },
            "Stories": {
                "Story": [{"#text": "Captain Lost"}, {"#text": "Science is Good"}]
            },
            "URL": "https://comicvine.gamespot.com/c/4000-145269/",
        }
    }
)

WRITE_METRON_DICT = create_write_dict(
    READ_METRON_DICT, MetronInfoSchema, "Notes", notes=METRON_NOTES
)
READ_METRON_STR = xmltodict.unparse(
    READ_METRON_DICT, pretty=True, short_empty_elements=True
)
WRITE_METRON_STR = xmltodict.unparse(
    WRITE_METRON_DICT, pretty=True, short_empty_elements=True
)

METRON_TESTER = TestParser(
    MetronInfoTransform,
    METRON_CBZ_FN,
    READ_METADATA,
    READ_METRON_DICT,
    READ_METRON_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_METRON_DICT,
    WRITE_METRON_STR,
)

SIMPLE_WRITE_METRON_DICT = create_write_dict(
    READ_METRON_DICT, MetronInfoSchema, "Notes", notes=METRON_NOTES
)
SIMPLE_READ_METRON_STR = xmltodict.unparse(
    SIMPLE_READ_METRON_DICT, pretty=True, short_empty_elements=True
)
SIMPLE_WRITE_METRON_STR = xmltodict.unparse(
    SIMPLE_WRITE_METRON_DICT, pretty=True, short_empty_elements=True
)


SIMPLE_METRON_TESTER = TestParser(
    MetronInfoTransform,
    METRON_CBZ_FN,
    READ_METADATA,
    SIMPLE_READ_METRON_DICT,
    SIMPLE_READ_METRON_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    SIMPLE_WRITE_METRON_DICT,
    SIMPLE_WRITE_METRON_STR,
)


def test_metron_from_metadata():
    """Test metadata import from comicbox.schemas."""
    METRON_TESTER.test_from_metadata()
    SIMPLE_METRON_TESTER.test_from_metadata()


def test_metron_from_dict():
    """Test native dict import."""
    METRON_TESTER.test_from_dict()
    SIMPLE_METRON_TESTER.test_from_dict()


def test_metron_from_string():
    """Test metadata import from string."""
    METRON_TESTER.test_from_string()
    SIMPLE_METRON_TESTER.test_from_string()


def test_metron_from_file():
    """Test metadata import from file."""
    METRON_TESTER.test_from_file()
    SIMPLE_METRON_TESTER.test_from_file()


def test_metron_to_dict():
    """Test metadata export to dict."""
    METRON_TESTER.test_to_dict()
    SIMPLE_METRON_TESTER.test_to_dict()


def test_metron_to_string():
    """Test metadata export to string."""
    test_str = METRON_TESTER.to_string()
    # with Path("/tmp/metron.xml").open("w") as f:
    #    f.write(test_str)

    # not tested just for diagnostic
    # xml_dict = xmltodict.parse(test_str)
    # diff = DeepDiff(dict(WRITE_METRON_DICT), xml_dict)
    # print(diff)

    METRON_TESTER.compare_string(test_str)

    simple_test_str = SIMPLE_METRON_TESTER.to_string()
    SIMPLE_METRON_TESTER.compare_string(simple_test_str)


def test_metron_to_file():
    """Test metadata export to file."""
    METRON_TESTER.test_to_file(export_fn="metroninfo-write.xml")
    SIMPLE_METRON_TESTER.test_to_file(export_fn="metroninfo-write.xml")


def test_metron_read():
    """Read RAR with METRON."""
    METRON_TESTER.test_md_read()
    SIMPLE_METRON_TESTER.test_md_read()


def test_metron_write():
    """Write cbz with METRON."""
    METRON_TESTER.test_md_write()
    SIMPLE_METRON_TESTER.test_md_write()
