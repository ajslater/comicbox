"""Test CIX module."""

from argparse import Namespace
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from glom import glom

from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.filename import FilenameSchema
from tests.util import TestParser

FN = "Captain Science #001 (1950) The Beginning - nothing.cbz"
READ_CONFIG = Namespace(comicbox=Namespace(read=["fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(read=["fn"], write=["fn"]))

SUB_DATA: Mapping[str, Any] = {
    "ext": "cbz",
    "issue": {
        "name": "001",
        "number": Decimal("1"),
    },
    "series": {"name": "Captain Science"},
    "stories": {"The Beginning - nothing": {}},
    "title": "The Beginning - nothing",
    "date": {
        "year": 1950,
    },
}
METADATA = MappingProxyType({ComicboxSchemaMixin.ROOT_TAG: SUB_DATA})
FILENAME_DICT = MappingProxyType(
    {
        FilenameSchema.ROOT_TAG: {
            "ext": "cbz",
            "issue": "001",
            "title": "The Beginning - nothing",
            "series": "Captain Science",
            "year": 1950,
        }
    }
)

FILENAME_STR = (
    f"{glom(SUB_DATA, 'series.name')} #{glom(SUB_DATA, 'issue.name')} ({glom(SUB_DATA, 'date.year')})"
    f" {next(iter(SUB_DATA['stories']))}.{SUB_DATA['ext']}"
)
FILENAME_STR_NO_REMAINDER = (
    f"{glom(SUB_DATA, 'series.name')} #{glom(SUB_DATA, 'issue.name')} ({glom(SUB_DATA, 'date.year')})"
    f" {next(iter(SUB_DATA['stories']))}.{SUB_DATA['ext']}"
)


FN_TESTER = TestParser(
    MetadataFormats.FILENAME,
    FN,
    METADATA,
    FILENAME_DICT,
    FILENAME_STR,
    READ_CONFIG,
    WRITE_CONFIG,
)


def test_filename_from_metadata():
    """Test metadata import from comicbox.schemas."""
    FN_TESTER.test_from_metadata()


def test_filename_from_dict():
    """Test metadata import from string."""
    FN_TESTER.test_from_dict()


def test_filename_from_string():
    """Test metadata import from string."""
    FN_TESTER.test_from_string()


def test_filename_from_file():
    """Test metadata import from file."""
    FN_TESTER.test_from_file()


def test_filename_to_dict():
    """Test metadata export to dict."""
    FN_TESTER.test_to_dict()


def test_filename_to_string():
    """Test metadata export to string."""
    FN_TESTER.test_to_string()


def test_filename_to_file():
    """Test metadata export to file."""
    FN_TESTER.test_to_file()


def test_filename_read():
    """Read comet metadata."""
    FN_TESTER.test_md_read()
