"""Test CBI module."""

from argparse import Namespace
from datetime import datetime
from types import MappingProxyType

import xmltodict

from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.pdf import PDFXmlSchema
from comicbox.schemas.xml_schemas import XML_UNPARSE_ARGS
from tests.const import PDF_FN
from tests.util import TestParser

READ_CONFIG = Namespace(comicbox=Namespace(read=("pdf", "fn")))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=("pdf", "cix"), read=["pdf"]))

METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "genres": {"Science Fiction": {}},
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00Z",
            "publisher": {"name": "SmallPub"},
            "scan_info": "Pages",
            "series": {"name": "test pdf"},
            "stories": {"the tangle of their lives": {}},
            "tags": {"d": {}, "e": {}, "f": {}},
            "tagger": "comicbox dev",
            "title": "the tangle of their lives",
            "updated_at": datetime(2025, 3, 2, 18, 33, 50),  # noqa: DTZ001
        }
    }
)
_ROOT_KEYPATH = PDFXmlSchema.ROOT_KEYPATH.split(".")
PDF_DICT = MappingProxyType(
    {
        PDFXmlSchema.ROOT_TAG: {
            "@x:xmptk": "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21",
            "@xmlns:x": "adobe:ns:meta/",
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "adobe:ns:meta/ http://ns.adobe.com/pdf/1.3/",
            _ROOT_KEYPATH[1]: {
                "@xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns",
                _ROOT_KEYPATH[2]: {
                    "@xmlns:pdf": "http://ns.adobe.com/pdf/1.3/",
                    "pdf:Author": "Jon Osterman",
                    "pdf:Creator": "Pages",
                    "pdf:Keywords": (
                        "<?xml "
                        'version="1.0" '
                        'encoding="UTF-8"?>\n'
                        "<ComicInfo "
                        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                        'xsi:schemaLocation="https://anansi-project.github.io/docs/comicinfo/schemas/v2.1 '
                        'https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd">\n'
                        "\t"
                        "<Title>the "
                        "tangle "
                        "of "
                        "their "
                        "lives</Title>\n"
                        "\t"
                        "<Series>test "
                        "pdf</Series>\n"
                        "\t"
                        "<Notes>Tagged "
                        "with "
                        "comicbox "
                        "dev "
                        "on "
                        "1970-01-01T00:00:00Z</Notes>\n"
                        "\t"
                        "<Writer>Jon "
                        "Osterman</Writer>\n"
                        "\t"
                        "<Publisher>SmallPub</Publisher>\n"
                        "\t"
                        "<Genre>Science "
                        "Fiction</Genre>\n"
                        "\t"
                        "<Tags>d,e,f</Tags>\n"
                        "\t"
                        "<ScanInformation>Pages</ScanInformation>\n"
                        "</ComicInfo>"
                    ),
                    "pdf:ModDate": "D:20250302183350+00'00'",
                    "pdf:Producer": "comicbox dev",
                    "pdf:Subject": "Science Fiction",
                    "pdf:Title": "the tangle of their lives",
                },
            },
        }
    }
)
PDF_STR = xmltodict.unparse(PDF_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType,reportCallIssue]

PDF_TESTER = TestParser(
    MetadataFormats.PDF_XML,
    PDF_FN,
    METADATA,
    PDF_DICT,
    PDF_STR,
    READ_CONFIG,
    WRITE_CONFIG,
)


def test_pdf_from_metadata():
    """Test metadata import from comicbox.schemas."""
    PDF_TESTER.test_from_metadata()


def test_pdf_from_dict():
    """Test native dict import."""
    PDF_TESTER.test_from_dict()


def test_pdf_from_string():
    """Test metadata import from string."""
    PDF_TESTER.test_from_string()


def test_pdf_from_file():
    """Test metadata import from file."""
    PDF_TESTER.test_from_file()


def test_pdf_to_dict():
    """Test metadata export to dict."""
    PDF_TESTER.test_to_dict(embed_fmt=MetadataFormats.COMIC_INFO)


def test_pdf_to_string():
    """Test metadata export to string."""
    PDF_TESTER.test_to_string(embed_fmt=MetadataFormats.COMIC_INFO)


def test_pdf_to_file():
    """Test metadata export to file."""
    PDF_TESTER.test_to_file(embed_fmt=MetadataFormats.COMIC_INFO)


def test_pdf_read():
    """Read PDF archive."""
    PDF_TESTER.test_pdf_read()


def test_pdf_write():
    """Write PDF metadata."""
    PDF_TESTER.test_pdf_write(page_count=1)
