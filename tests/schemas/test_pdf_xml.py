"""Test CBI module."""
from argparse import Namespace
from types import MappingProxyType

import xmltodict

from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.pdf import PDFXmlSchema
from comicbox.transforms.pdf import PDFXmlTransform
from tests.const import PDF_FN
from tests.util import TestParser

READ_CONFIG = Namespace(comicbox=Namespace(read=["pdf"], compute_pages=False))
WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=["pdf"], read=["pdf"], compute_pages=False)
)

METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "contributors": {"writer": {"Jon Osterman"}},
            "scan_info": "Pages",
            "genres": {"Science Fiction"},
            "tags": {"d", "e", "f"},
            "title": "the tangle of their lives",
            "tagger": "comicbox dev",
        }
    }
)
PDF_DICT = MappingProxyType(
    {
        PDFXmlSchema.ROOT_TAGS[0]: {
            "@x:xmptk": "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21",
            "@xmlns:x": "adobe:ns:meta/",
            "@xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@xsi:schemaLocation": "http://ns.adobe.com/pdf/1.3/",
            PDFXmlSchema.ROOT_TAGS[1]: {
                "@xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns",
                PDFXmlSchema.ROOT_TAGS[2]: {
                    "@xmlns:pdf": "http://ns.adobe.com/pdf/1.3/",
                    "pdf:Author": "Jon Osterman",
                    "pdf:Creator": "Pages",
                    "pdf:Keywords": "d,e,f",
                    "pdf:Producer": "comicbox dev",
                    "pdf:Subject": "Science Fiction",
                    "pdf:Title": "the tangle of their lives",
                },
            },
        }
    }
)
PDF_STR = xmltodict.unparse(PDF_DICT, pretty=True, short_empty_elements=True)

PDF_TESTER = TestParser(
    PDFXmlTransform,
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
    PDF_TESTER.test_to_dict()


def test_pdf_to_string():
    """Test metadata export to string."""
    PDF_TESTER.test_to_string()


def test_pdf_to_file():
    """Test metadata export to file."""
    PDF_TESTER.test_to_file()


def test_pdf_read():
    """Read PDF archive."""
    PDF_TESTER.test_md_read()


def test_pdf_write():
    """Write PDF metadata."""
    PDF_TESTER.test_pdf_write()
