"""Test CIX module."""

import os
from argparse import Namespace
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from glom import glom

from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.filename.schema import FilenameSchema
from tests.util import TestParser

FN = "Captain Science #001 (1950) The Beginning - nothing.cbz"
READ_CONFIG = get_config(Namespace(comicbox=Namespace(read=Namespace(formats=["fn"]))))
WRITE_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            read=Namespace(formats=["fn"]), write=Namespace(formats=["fn"])
        )
    )
)

SUB_DATA: Mapping[str, Any] = {
    "ext": "cbz",
    "issue": {
        "name": "001",
        "number": Decimal(1),
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


def test_filename_from_metadata() -> None:
    """Test metadata import from comicbox.formats.base.schemas."""
    FN_TESTER.test_from_metadata()


def test_filename_from_dict() -> None:
    """Test metadata import from string."""
    FN_TESTER.test_from_dict()


def test_filename_from_string() -> None:
    """Test metadata import from string."""
    FN_TESTER.test_from_string()


def test_filename_from_file() -> None:
    """Test metadata import from file."""
    FN_TESTER.test_from_file()


def test_filename_to_dict() -> None:
    """Test metadata export to dict."""
    FN_TESTER.test_to_dict()


def test_filename_to_string() -> None:
    """Test metadata export to string."""
    FN_TESTER.test_to_string()


def test_filename_to_file() -> None:
    """Test metadata export to file."""
    FN_TESTER.test_to_file()


def test_filename_read() -> None:
    """Read comet metadata."""
    FN_TESTER.test_md_read()


def test_filename_dumps_sanitizes_path_separators() -> None:
    """A field value with a path separator must not escape the basename."""
    obj = {
        FilenameSchema.ROOT_TAG: {
            "ext": "cbz",
            "issue": "001",
            "series": f"Foo{os.sep}Bar",
            "year": 1950,
        }
    }
    fn = FilenameSchema().dumps(obj)

    assert os.sep not in fn
    if os.altsep:
        assert os.altsep not in fn
    assert "Foo_Bar" in fn
    assert fn.endswith(".cbz")
    # The result is a single path component, not a nested path.
    assert Path(fn).name == fn


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ("Batman: Year One", "Batman Year One #001 (1950).cbz"),
        ("Re:Zero", "Re-Zero #001 (1950).cbz"),
        ("Foo\\Bar", "Foo_Bar #001 (1950).cbz"),
        ('What If? "*<Foo>|"', "What If Foo #001 (1950).cbz"),
    ],
)
def test_filename_dumps_sanitizes_reserved_chars(series: str, expected: str) -> None:
    """Characters SMB and Windows can't store are replaced on every platform."""
    obj = {
        FilenameSchema.ROOT_TAG: {
            "ext": "cbz",
            "issue": "001",
            "series": series,
            "year": 1950,
        }
    }

    assert FilenameSchema().dumps(obj) == expected


def test_filename_sanitized_colon_reads_back_as_one_series() -> None:
    """A colon dropped from the series must not split it on the way back in."""
    obj = {
        FilenameSchema.ROOT_TAG: {
            "ext": "cbz",
            "issue": "005",
            "series": "Star Wars: Doctor Aphra",
            "year": 2017,
        }
    }
    schema = FilenameSchema()
    fn = schema.dumps(obj)

    assert glom(schema.loads(fn), f"{FilenameSchema.ROOT_TAG}.series") == (
        "Star Wars Doctor Aphra"
    )
