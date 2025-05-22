"""Test CBI module."""

from argparse import Namespace
from datetime import datetime
from types import MappingProxyType

import simplejson as json

from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.pdf import MuPDFSchema
from tests.const import PDF_FN
from tests.util import TestParser

READ_CONFIG = Namespace(comicbox=Namespace(read=["pdf", "fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["pdf", "cix"], read=["pdf"]))

METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "scan_info": "Pages",
            "genres": {"Science Fiction": {}},
            "publisher": {"name": "SmallPub"},
            "series": {"name": "test pdf"},
            "stories": {"the tangle of their lives": {}},
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00",
            "tagger": "comicbox dev",
            "tags": {"d": {}, "e": {}, "f": {}},
            "title": "the tangle of their lives",
            "updated_at": datetime(1970, 1, 1, 0, 0, 0),  # noqa: DTZ001
        }
    }
)
PDF_DICT = MappingProxyType(
    {
        MuPDFSchema.ROOT_TAG: {
            "author": "Jon Osterman",
            "creator": "Pages",
            "keywords": (
                "<?xml "
                'version="1.0" '
                'encoding="UTF-8"?>\n'
                "<ComicInfo "
                'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:schemaLocation="https://anansi-project.github.io/docs/comicinfo/schemas/v2.1 https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd">\n\t'
                "<Title>the tangle of their lives</Title>\n\t"
                "<Series>test pdf</Series>\n\t"
                "<Notes>Tagged with comicbox dev on 1970-01-01T00:00:00</Notes>\n\t"
                "<Writer>Jon Osterman</Writer>\n\t"
                "<Publisher>SmallPub</Publisher>\n\t"
                "<Genre>Science Fiction</Genre>\n\t"
                "<Tags>d,e,f</Tags>\n\t"
                "<ScanInformation>Pages</ScanInformation>\n"
                "</ComicInfo>"
            ),
            "modDate": "D:19700101000000+00'00'",
            "producer": "comicbox dev",
            "subject": "Science Fiction",
            "title": "the tangle of their lives",
        }
    }
)
PDF_STR = json.dumps(dict(PDF_DICT), sort_keys=True, indent=2)

PDF_TESTER = TestParser(
    MetadataFormats.PDF,
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
