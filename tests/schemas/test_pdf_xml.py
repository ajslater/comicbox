"""Test CBI module."""

from argparse import Namespace
from datetime import datetime, timezone
from types import MappingProxyType

import xmltodict

from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.pdf import PDFXmlSchema
from comicbox.schemas.xml_schemas import XML_UNPARSE_ARGS
from tests.util import TestParser

PDF_CIX_FN = "test_cix.pdf"
PDF_KW_FN = "test_pdf_legacy_keywords.pdf"
PDF_FN = "test_pdf.pdf"

READ_CONFIG = get_config(Namespace(comicbox=Namespace(read=["pdf", "cix"])))
WRITE_CONFIG = get_config(
    Namespace(comicbox=Namespace(write=["pdf", "cix"], read=["pdf", "cix"]))
)
PDF_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "genres": {"Science Fiction": {}},
            "scan_info": "Pages",
            "stories": {"the tangle of their lives": {}},
            "tagger": "comicbox dev",
            "tags": {"d": {}, "e": {}, "f": {}},
            "title": "the tangle of their lives",
            "updated_at": datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        }
    }
)
CIX_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "scan_info": "Pages",
            "genres": {"Science Fiction": {}},
            "publisher": {"name": "SmallPub"},
            "stories": {"the tangle of their lives": {}},
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00",
            "page_count": 4,
            "tagger": "comicbox dev",
            "tags": {"d": {}, "e": {}, "f": {}},
            "title": "the tangle of their lives",
            "updated_at": datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        }
    }
)
_ROOT_KEYPATH = PDFXmlSchema.ROOT_KEYPATH.split(".")
PDF_KW_DICT = MappingProxyType(
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
                        'xsi:schemaLocation="https://anansi-project.github.io/docs/comicinfo/schemas/v2.1 https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd">\n\t'
                        "<Title>the tangle of their lives</Title>\n\t"
                        "<Notes>Tagged with comicbox dev on 1970-01-01T00:00:00</Notes>\n\t"
                        "<Writer>Jon Osterman</Writer>\n\t"
                        "<Publisher>SmallPub</Publisher>\n\t"
                        "<Genre>Science Fiction</Genre>\n\t"
                        "<Tags>d,e,f</Tags>\n\t"
                        "<PageCount>4</PageCount>\n\t"
                        "<ScanInformation>Pages</ScanInformation>\n"
                        "</ComicInfo>"
                    ),
                    "pdf:ModDate": "D:19700101000000+00'00'",
                    "pdf:Producer": "comicbox dev",
                    "pdf:Subject": "Science Fiction",
                    "pdf:Title": "the tangle of their lives",
                },
            },
        }
    }
)
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
                    "pdf:Keywords": "d,e,f",
                    "pdf:ModDate": "D:19700101000000+00'00'",
                    "pdf:Producer": "comicbox dev",
                    "pdf:Subject": "Science Fiction",
                    "pdf:Title": "the tangle of their lives",
                },
            },
        }
    }
)
CIX_DICT = MappingProxyType(
    {
        "ComicInfo": {
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1 https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd",
            "Title": "the tangle of their lives",
            "Notes": "Tagged with comicbox dev on 1970-01-01T00:00:00",
            "Writer": "Jon Osterman",
            "Publisher": "SmallPub",
            "Genre": "Science Fiction",
            "Tags": "d,e,f",
            "PageCount": 4,
            "ScanInformation": "Pages",
        }
    }
)
PDF_STR = xmltodict.unparse(PDF_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]
PDF_KW_STR = xmltodict.unparse(PDF_KW_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]
CIX_STR = xmltodict.unparse(CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue]

PDF_METADATA_TESTER = TestParser(
    MetadataFormats.PDF_XML,
    PDF_FN,
    PDF_METADATA,
    PDF_DICT,
    PDF_STR,
    READ_CONFIG,
    WRITE_CONFIG,
)

PDF_KW_TESTER = TestParser(
    MetadataFormats.PDF_XML,
    PDF_KW_FN,
    CIX_METADATA,
    PDF_KW_DICT,
    PDF_KW_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    export_fn="pdf-nested.xml",
)


PDF_CIX_TESTER = TestParser(
    MetadataFormats.COMIC_INFO,
    PDF_CIX_FN,
    CIX_METADATA,
    CIX_DICT,
    CIX_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    export_fn="pdf-cix.xml",
)


def test_pdf_from_metadata():
    """Test metadata import from comicbox.schemas."""
    PDF_METADATA_TESTER.test_from_metadata()


def test_pdf_from_metadata_kw():
    """Test metadata import from comicbox.schemas."""
    PDF_KW_TESTER.test_from_metadata()


def test_pdf_from_metadata_cix():
    """Test metadata import from comicbox.schemas."""
    PDF_CIX_TESTER.test_from_metadata()


def test_pdf_from_dict():
    """Test native dict import."""
    PDF_METADATA_TESTER.test_from_dict()


def test_pdf_from_dict_kw():
    """Test native dict import."""
    PDF_KW_TESTER.test_from_dict()


def test_pdf_from_string():
    """Test metadata import from string."""
    PDF_METADATA_TESTER.test_from_string()


def test_pdf_from_string_kw():
    """Test metadata import from string."""
    PDF_KW_TESTER.test_from_string()


def test_pdf_from_file():
    """Test metadata import from file."""
    PDF_METADATA_TESTER.test_from_file()


def test_pdf_from_file_kw():
    """Test metadata import from file."""
    PDF_KW_TESTER.test_from_file()


def test_pdf_from_file_cix():
    """Test metadata import from file."""
    PDF_CIX_TESTER.test_from_file()


def test_pdf_to_dict():
    """Test metadata export to dict."""
    PDF_METADATA_TESTER.test_to_dict()


def test_pdf_to_dict_cix():
    """Test metadata export to dict."""
    PDF_CIX_TESTER.test_to_dict()


def test_pdf_to_string():
    """Test metadata export to string."""
    PDF_METADATA_TESTER.test_to_string()


def test_pdf_to_string_cix():
    """Test metadata export to string."""
    PDF_CIX_TESTER.test_to_string()


def test_pdf_to_file():
    """Test metadata export to file."""
    PDF_METADATA_TESTER.test_to_file()


def test_pdf_to_file_cix():
    """Test metadata export to file."""
    PDF_CIX_TESTER.test_to_file()


def test_pdf_read():
    """Read PDF archive."""
    PDF_METADATA_TESTER.test_pdf_read()


def test_pdf_read_kw():
    """Read PDF archive."""
    PDF_KW_TESTER.test_pdf_read()


def test_pdf_read_cix():
    """Read PDF archive."""
    PDF_CIX_TESTER.test_pdf_read()


def test_pdf_write():
    """Write PDF metadata."""
    PDF_METADATA_TESTER.test_pdf_write(page_count=1)


def test_pdf_write_cix():
    """Write PDF metadata."""
    PDF_CIX_TESTER.test_pdf_write(page_count=1)
