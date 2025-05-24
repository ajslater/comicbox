"""Test MetronInfo Schema."""

from argparse import Namespace
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import MappingProxyType

import xmltodict
from glom import Assign, glom

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.schemas.xml_schemas import XML_UNPARSE_ARGS
from tests.const import METRON_CBZ_FN, TEST_DATETIME, TEST_DTTM_STR
from tests.util import (
    TestParser,
    assert_diff,
    create_write_dict,
    create_write_metadata,
)

READ_CONFIG = Namespace(comicbox=Namespace(read=["mi", "fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["mi"], read=["mi"]))
METRON_NOTES = (
    "Tagged with "
    "comicbox dev "
    "on "
    "1970-01-01T00:00:00Z "
    "[Issue ID 145269] "
    "urn:comicvine:145269 "
    "urn:isbn:123-456789-0123 "
    "urn:upc:12345 "
    "urn:metron:999999"
)
READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "age_rating": "Teen Plus",
            "arcs": {
                "Captain Arc": {"number": 4},
                "Other Arc": {"number": 2},
            },
            "date": {
                "cover_date": date(1950, 11, 1),
                "day": 1,
                "month": 11,
                "year": 1950,
            },
            "characters": {
                "Captain Science": {},
                "Gordon Dane": {},
            },
            "collection_title": "Omnibus",
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "genres": {"Science Fiction": {}},
            "imprint": {
                "identifiers": {
                    "metron": {
                        "id_key": "222",
                        "url": "https://metron.cloud/imprint/222",
                    },
                },
                "name": "Youthful Imprint",
            },
            "identifier_primary_source": {
                "id_source": "metron",
                "url": "https://metron.cloud/",
            },
            "identifiers": {
                "comicvine": {
                    "id_key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "isbn": {
                    "id_key": "123-456789-0123",
                    "url": "https://isbndb.com/book/123-456789-0123",
                },
                "metron": {
                    "id_key": "999999",
                    "url": "https://metron.cloud/issue/999999",
                },
                "upc": {"id_key": "12345", "url": "https://barcodelookup.com/12345"},
            },
            "issue": {
                "name": "1",
                "number": Decimal("1"),
            },
            "language": "en",
            "notes": METRON_NOTES,
            "original_format": "Single Issue",
            "page_count": 0,
            "prices": {
                "GB": Decimal("0.5").quantize(Decimal("0.01")),
                "US": Decimal("1.25").quantize(Decimal("0.01")),
            },
            "publisher": {
                "identifiers": {
                    "metron": {
                        "id_key": "11",
                        "url": "https://metron.cloud/publisher/11",
                    },
                },
                "name": "Youthful Adventure Stories",
            },
            "series": {
                "identifiers": {
                    "metron": {
                        "id_key": "2222",
                        "url": "https://metron.cloud/series/2222",
                    }
                },
                "name": "Captain Science",
                "sort_name": "Captain Science",
                "start_year": 1950,
                "volume_count": 1,
            },
            "stories": {
                "Captain Lost": {
                    "identifiers": {
                        "metron": {
                            "id_key": "5555",
                            "url": "https://metron.cloud/story/5555",
                        }
                    },
                },
                "Science is Good": {},
                "metron": {},
            },
            "title": "Captain Lost; Science is Good; metron",
            "reprints": [
                {"language": "es", "series": {"name": "Capitán Ciencia"}},
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"},
            ],
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
            "universes": {"Mirror": {"designation": "4242"}},
            "volume": {
                "number": 1950,
                "number_to": 1952,
                "issue_count": 10,
            },
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA, notes=METRON_NOTES)

READ_METRON_DICT = MappingProxyType(
    {
        MetronInfoSchema.ROOT_TAG: {
            "@xmlns:metroninfo": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0",
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0 https://raw.githubusercontent.com/Metron-Project/metroninfo/refs/heads/master/schema/v1.0/MetronInfo.xsd",
            "AgeRating": "Teen Plus",
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
                    {"@source": "Comic Vine", "#text": "145269"},
                    {"@primary": "true", "@source": "Metron", "#text": "999999"},
                ],
            },
            "LastModified": TEST_DTTM_STR,
            "MangaVolume": "1950-1952",
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Prices": {
                "Price": [
                    {"#text": "0.50", "@country": "GB"},
                    {"#text": "1.25", "@country": "US"},
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
                    {"#text": "metron"},
                ]
            },
            "URLs": {
                "URL": [
                    {"#text": "https://barcodelookup.com/12345"},
                    {"#text": "https://comicvine.gamespot.com/c/4000-145269/"},
                    {"#text": "https://isbndb.com/book/123-456789-0123"},
                    {"#text": "https://metron.cloud/issue/999999", "@primary": "true"},
                ]
            },
            "Universes": {"Universe": [{"Designation": "4242", "Name": "Mirror"}]},
        }
    }
)
SIMPLE_READ_METRON_DICT = MappingProxyType(
    {
        MetronInfoSchema.ROOT_TAG: {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0",
            "AgeRating": "Teen Plus",
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
                    {"@primary": "true", "@source": "Metron", "#text": "999999"},
                    {"@source": "Comic Vine", "#text": "145269"},
                ],
            },
            "LastModified": TEST_DTTM_STR,
            "MangaVolume": "1950-1952",
            "Notes": METRON_NOTES,
            "Number": "1",
            "PageCount": 0,
            "Prices": {
                "Price": [
                    {"#text": "0.50", "@country": "GB"},
                    {"#text": "1.25", "@country": "US"},
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
                    "metron",
                ]
            },
            "Universes": {"Universe": [{"Name": "Mirror", "Designation": "4242"}]},
            "URLs": {
                "URL": [
                    {"#text": "https://barcodelookup.com/12345"},
                    {"#text": "https://comicvine.gamespot.com/c/4000-145269/"},
                    {"#text": "https://isbndb.com/book/123-456789-0123"},
                    {"#text": "https://metron.cloud/issue/999999", "@primary": "true"},
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
    prices = glom(stringified_data, f"{MetronInfoSchema.ROOT_TAG}.Prices.Price")
    for price in prices:
        price["#text"] = str(price["#text"])
    glom(
        stringified_data,
        Assign(f"{MetronInfoSchema.ROOT_TAG}.Prices.Price", prices, missing=dict),
    )
    return xmltodict.unparse(stringified_data, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]


READ_METRON_STR = unparse_strinfigy_decimals(READ_METRON_DICT)
WRITE_METRON_STR = unparse_strinfigy_decimals(WRITE_METRON_DICT)

METRON_TESTER = TestParser(
    MetadataFormats.METRON_INFO,
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
    MetadataFormats.METRON_INFO,
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

URL_PRIMARY_READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifier_primary_source": {
                "id_source": "metron",
                "url": "https://metron.cloud/",
            },
            "identifiers": {
                "comicvine": {
                    "id_key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "isbn": {
                    "id_key": "123-456789-0123",
                    "url": "https://isbndb.com/book/123-456789-0123",
                },
                "metron": {
                    "id_key": "999999",
                    "url": "https://metron.cloud/issue/999999",
                },
                "upc": {"id_key": "12345", "url": "https://barcodelookup.com/12345"},
            },
        }
    }
)
URL_PRIMARY_READ_METRON_DICT = MappingProxyType(
    {
        MetronInfoSchema.ROOT_TAG: {
            "@xmlns:metroninfo": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0",
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://metron-project.github.io/docs/metroninfo/schemas/v1.0 https://raw.githubusercontent.com/Metron-Project/metroninfo/refs/heads/master/schema/v1.0/MetronInfo.xsd",
            "URLs": {
                "URL": [
                    {"#text": "https://barcodelookup.com/12345"},
                    {"#text": "https://comicvine.gamespot.com/c/4000-145269/"},
                    {"#text": "https://isbndb.com/book/123-456789-0123"},
                    {"#text": "https://metron.cloud/issue/999999", "@primary": "true"},
                ]
            },
        }
    }
)


def test_metron_from_metadata():
    """Test metadata import from comicbox.schemas."""
    METRON_TESTER.test_from_metadata()
    SIMPLE_METRON_TESTER.test_from_metadata()


def test_metron_from_dict():
    """Test native dict import."""
    METRON_TESTER.test_from_dict()
    SIMPLE_METRON_TESTER.test_from_dict()


def test_metron_from_dict_url_primary():
    """Test getting ips from urls."""
    config = Namespace(
        comicbox=Namespace(
            metadata=URL_PRIMARY_READ_METRON_DICT,
            metadat_format=MetadataFormats.METRON_INFO,
            print="sncmp",
        )
    )
    with Comicbox(config=config) as car:
        car.print_out()
        md = car.get_metadata()

    assert_diff(URL_PRIMARY_READ_METADATA, md)


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
    METRON_TESTER.compare_string(test_str)

    simple_test_str = SIMPLE_METRON_TESTER.to_string()
    SIMPLE_METRON_TESTER.compare_string(simple_test_str)


def test_metron_to_file():
    """Test metadata export to file."""
    METRON_TESTER.test_to_file(export_fn="metroninfo-write.xml")
    SIMPLE_METRON_TESTER.test_to_file(export_fn="metroninfo-write.xml")


def test_metron_read():
    """Read cbz with METRON."""
    METRON_TESTER.test_md_read()
    SIMPLE_METRON_TESTER.test_md_read()


def test_metron_write():
    """Write cbz with METRON."""
    METRON_TESTER.test_md_write()
    SIMPLE_METRON_TESTER.test_md_write()
