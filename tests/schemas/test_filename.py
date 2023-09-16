"""Test CIX module."""
from argparse import Namespace
from decimal import Decimal
from types import MappingProxyType

from comicbox.schemas.filename import FilenameSchema
from tests.util import TestParser

FN = "Captain Science #001 (1950) The Beginning - nothing.cbz"
READ_CONFIG = Namespace(comicbox=Namespace(read=["fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(read=["fn"], write=["fn"]))

METADATA = MappingProxyType(
    {
        "ext": "cbz",
        "issue": "001",
        "issue_number": Decimal("1"),
        "title": "The Beginning",
        "series": "Captain Science",
        "year": 1950,
        "remainders": ["nothing"],
    }
)

FILENAME_DICT = MappingProxyType(
    {
        "filename": {
            "ext": "cbz",
            "issue": "001",
            "title": "The Beginning",
            "series": "Captain Science",
            "year": 1950,
            "remainders": ["nothing"],
        }
    }
)

_REMAINDERS_STR = " ".join(METADATA["remainders"])  # type: ignore
FILENAME_STR = (
    f"{METADATA['series']} #{METADATA['issue']} ({METADATA['year']})"
    f" {METADATA['title']} - {_REMAINDERS_STR}.{METADATA['ext']}"
)
FILENAME_STR_NO_REMAINDER = (
    f"{METADATA['series']} #{METADATA['issue']} ({METADATA['year']})"
    f" {METADATA['title']}.{METADATA['ext']}"
)


FN_TESTER = TestParser(
    FilenameSchema,
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
