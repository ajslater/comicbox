"""Test CBI module."""

from argparse import Namespace
from datetime import datetime, timezone
from types import MappingProxyType

import simplejson as json
import xmltodict

from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.xml_schemas import XML_UNPARSE_ARGS
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.pdf.schema import MuPDFSchema
from tests.util import TestParser

PDF_CIX_FN = "test_cix.pdf"
PDF_FN = "test_pdf.pdf"

READ_CONFIG = get_config(
    Namespace(comicbox=Namespace(read=Namespace(formats=["pdf", "cix"])))
)
WRITE_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            read=Namespace(formats=["pdf", "cix"]),
            write=Namespace(formats=["pdf", "cix"]),
        )
    )
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
PDF_DICT = MappingProxyType(
    {
        MuPDFSchema.ROOT_TAG: {
            "author": "Jon Osterman",
            "creator": "Pages",
            "keywords": "d,e,f",
            "modDate": "D:19700101000000+00'00'",
            "producer": "comicbox dev",
            "subject": "Science Fiction",
            "title": "the tangle of their lives",
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
PDF_STR = json.dumps(dict(PDF_DICT), sort_keys=True, indent=2)
CIX_STR = xmltodict.unparse(CIX_DICT, **XML_UNPARSE_ARGS)  # pyright: ignore[reportArgumentType, reportCallIssue], # ty: ignore[no-matching-overload]

PDF_METADATA_TESTER = TestParser(
    MetadataFormats.PDF,
    PDF_FN,
    PDF_METADATA,
    PDF_DICT,
    PDF_STR,
    READ_CONFIG,
    WRITE_CONFIG,
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


def test_pdf_from_metadata() -> None:
    """Test metadata import from comicbox.formats.base.schemas."""
    PDF_METADATA_TESTER.test_from_metadata()


def test_pdf_from_metadata_cix() -> None:
    """Test metadata import from comicbox.formats.base.schemas."""
    PDF_CIX_TESTER.test_from_metadata()


def test_pdf_from_dict() -> None:
    """Test native dict import."""
    PDF_METADATA_TESTER.test_from_dict()


def test_pdf_from_string() -> None:
    """Test metadata import from string."""
    PDF_METADATA_TESTER.test_from_string()


def test_pdf_from_file() -> None:
    """Test metadata import from file."""
    PDF_METADATA_TESTER.test_from_file()


def test_pdf_from_file_cix() -> None:
    """Test metadata import from file."""
    PDF_CIX_TESTER.test_from_file()


def test_pdf_to_dict() -> None:
    """Test metadata export to dict."""
    PDF_METADATA_TESTER.test_to_dict()


def test_pdf_to_dict_cix() -> None:
    """Test metadata export to dict."""
    PDF_CIX_TESTER.test_to_dict()


def test_pdf_to_string() -> None:
    """Test metadata export to string."""
    PDF_METADATA_TESTER.test_to_string()


def test_pdf_to_string_cix() -> None:
    """Test metadata export to string."""
    PDF_CIX_TESTER.test_to_string()


def test_pdf_to_file() -> None:
    """Test metadata export to file."""
    PDF_METADATA_TESTER.test_to_file()


def test_pdf_to_file_cix() -> None:
    """Test metadata export to file."""
    PDF_CIX_TESTER.test_to_file()


def test_pdf_read() -> None:
    """Read PDF archive."""
    PDF_METADATA_TESTER.test_pdf_read()


def test_pdf_read_cix() -> None:
    """Read PDF archive."""
    PDF_CIX_TESTER.test_pdf_read()


def test_pdf_write() -> None:
    """Write PDF metadata."""
    PDF_METADATA_TESTER.test_pdf_write(page_count=1)


def test_pdf_write_cix() -> None:
    """Write PDF metadata."""
    PDF_CIX_TESTER.test_pdf_write(page_count=1)
