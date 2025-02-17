"""Test METRON module."""

from argparse import Namespace
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict

from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.transforms.metroninfo import PRICE_TAG, PRICES_TAG, MetronInfoTransform
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
    "[Issue ID 145269] "
    "urn:comicvine:145269 "
    "urn:isbn:123-456789-0123 "
    "urn:upc:12345 "
    "urn:metron:999999"
)
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "date": date(year=1950, month=11, day=1),
            "characters": [
                {"name": "Captain Science"},
                {"name": "Gordon Dane"},
            ],
            "collection_title": "Omnibus",
            "contributors": {
                "inker": {"Wally Wood"},
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "genres": [{"name": "Science Fiction"}],
            "imprint": {
                "identifiers": {
                    "metron": {"nss": "222", "url": "https://metron.cloud/imprint/222"},
                },
                "name": "Youthful Imprint",
            },
            "identifier_primary_source": {
                "nid": "metron",
                "url": "https://metron.cloud/",
            },
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "metron": {
                    "nss": "999999",
                    "url": "https://metron.cloud/issue/999999",
                },
                "upc": {"nss": "12345", "url": "https://barcodelookup.com/12345"},
                "isbn": {
                    "nss": "123-456789-0123",
                    "url": "https://isbndb.com/book/123-456789-0123",
                },
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "notes": METRON_NOTES,
            "original_format": "Single Issue",
            "page_count": 0,
            "prices": [
                {"country": "US", "price": Decimal("1.25").quantize(Decimal("0.01"))},
                {"country": "GB", "price": Decimal("0.5").quantize(Decimal("0.01"))},
            ],
            "publisher": {
                "identifiers": {
                    "metron": {"nss": "11", "url": "https://metron.cloud/publisher/11"},
                },
                "name": "Youthful Adventure Stories",
            },
            "series": {
                "identifiers": {
                    "metron": {"nss": "2222", "url": "https://metron.cloud/series/2222"}
                },
                "name": "Captain Science",
                "sort_name": "Captain Science",
                "start_year": 1950,
                "volume_count": 1,
            },
            "stories": [
                {
                    "identifiers": {
                        "metron": {
                            "nss": "5555",
                            "url": "https://metron.cloud/story/5555",
                        }
                    },
                    "name": "Captain Lost",
                },
                {"name": "Science is Good"},
            ],
            "story_arcs": {
                "Captain Arc": 4,
                "Other Arc": 2,
            },
            "reprints": [
                {"language": "es", "series": {"name": "Capitán Ciencia"}},
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"},
            ],
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
            "volume": {
                "name": "NineteenFifty",
                "number": 1950,
                "issue_count": 10,
            },
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
            "CollectionTitle": "Omnibus",
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
            "IDS": {
                "ID": [
                    {"@source": "Metron", "#text": "999999", "@primary": True},
                    {"@source": "Comic Vine", "#text": "145269"},
                ],
            },
            "MangaVolume": "NineteenFifty",
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Prices": {
                "Price": [
                    {"#text": "1.25", "@country": "US"},
                    {"#text": "0.50", "@country": "GB"},
                ]
            },
            "Publisher": {
                "@id": "11",
                "Imprint": {"@id": "222", "#text": "Youthful Imprint"},
                "Name": "Youthful Adventure Stories",
            },
            "Reprints": {
                "Reprint": [
                    {"#text": "Capitán Ciencia"},
                    {"#text": "Captain Science Alternate #001"},
                ]
            },
            "Series": {
                "@id": "2222",
                "@lang": "en",
                "AlternativeNames": {
                    "AlternativeName": [
                        {"#text": "Capitán Ciencia", "@lang": "es"},
                        {"#text": "Captain Science Alternate"},
                    ]
                },
                "Format": "Single Issue",
                "IssueCount": 10,
                "Name": "Captain Science",
                "SortName": "Captain Science",
                "StartYear": 1950,
                "Volume": 1950,
                "VolumeCount": 1,
            },
            "Stories": {
                "Story": [
                    {"@id": "5555", "#text": "Captain Lost"},
                    {"#text": "Science is Good"},
                ]
            },
            "URLs": {
                "URL": [
                    {"#text": "https://metron.cloud/issue/999999", "@primary": True},
                    {"#text": "https://comicvine.gamespot.com/c/4000-145269/"},
                    {"#text": "https://isbndb.com/book/123-456789-0123"},
                    {"#text": "https://barcodelookup.com/12345"},
                ]
            },
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
            "CollectionTitle": "Omnibus",
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
            "Genres": {"Genre": ["Science Fiction"]},
            "IDS": {
                "ID": [
                    {"@source": "Comic Vine", "#text": "145269"},
                    {"@source": "Metron", "#text": "999999", "@primary": True},
                ],
            },
            "MangaVolume": "NineteenFifty",
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Prices": {
                "Price": [
                    {"#text": "1.25", "@country": "US"},
                    {"#text": "0.50", "@country": "GB"},
                ]
            },
            "Publisher": {
                "@id": "11",
                "Imprint": {"@id": "222", "#text": "Youthful Imprint"},
                "Name": "Youthful Adventure Stories",
            },
            "Reprints": {
                "Reprint": [
                    {"#text": "Capitán Ciencia"},
                    {"#text": "Captain Science Alternate #001"},
                ]
            },
            "Series": {
                "@id": "2222",
                "@lang": "en",
                "AlternativeNames": {
                    "AlternativeName": [
                        {"#text": "Capitán Ciencia", "@lang": "es"},
                        {"#text": "Captain Science Alternate"},
                    ]
                },
                "Format": "Single Issue",
                "IssueCount": 10,
                "Name": "Captain Science",
                "SortName": "Captain Science",
                "StartYear": 1950,
                "Volume": 1950,
                "VolumeCount": 1,
            },
            "Stories": {
                "Story": [
                    {"@id": "5555", "#text": "Captain Lost"},
                    "Science is Good",
                ]
            },
            "URLs": {
                "URL": [
                    {"#text": "https://metron.cloud/issue/999999", "@primary": True},
                    {"#text": "https://comicvine.gamespot.com/c/4000-145269/"},
                    {"#text": "https://isbndb.com/book/123-456789-0123"},
                    {"#text": "https://barcodelookup.com/12345"},
                ]
            },
        }
    }
)

WRITE_METRON_DICT = create_write_dict(
    READ_METRON_DICT, MetronInfoSchema, "Notes", notes=METRON_NOTES
)


def unparse_strinfigy_decimals(data):
    """Stringify decimals for xmltodict."""
    stringified_data = deepcopy(dict(data))
    prices = stringified_data[MetronInfoSchema.ROOT_TAGS[0]][PRICES_TAG][PRICE_TAG]
    for price in prices:
        price["#text"] = str(price["#text"])
    stringified_data[MetronInfoSchema.ROOT_TAGS[0]][PRICES_TAG][PRICE_TAG] = prices
    return xmltodict.unparse(stringified_data, pretty=True, short_empty_elements=True)


READ_METRON_STR = unparse_strinfigy_decimals(READ_METRON_DICT)
WRITE_METRON_STR = unparse_strinfigy_decimals(WRITE_METRON_DICT)

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
SIMPLE_READ_METRON_STR = unparse_strinfigy_decimals(SIMPLE_READ_METRON_DICT)
SIMPLE_WRITE_METRON_STR = unparse_strinfigy_decimals(SIMPLE_WRITE_METRON_DICT)


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
    from pprint import pprint

    print("READ")
    pprint(METRON_TESTER.read_reference_native_dict)
    METRON_TESTER.test_from_string()
    print("SIMPLE_READ")
    pprint(SIMPLE_METRON_TESTER.read_reference_native_dict)
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
