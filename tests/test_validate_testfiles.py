"""Validate test metadata files."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

import os
from pathlib import Path

from comicbox.box.validate import validate_source
from tests.const import TEST_EXPORT_DIR, TEST_METADATA_DIR

_NUM_TEST_FILES = 16
_SUFFIXES = frozenset({"." + ext for ext in ("txt", "xml", "json", "yaml", "yml")})


def _test_dir(root_dir: "pathlib.PosixPath", substring: str="") -> "set[pathlib.PosixPath]":
    validated = set()
    for root, _, fns in os.walk(root_dir):
        root_path = Path(root)
        for fn in fns:
            if substring and (substring not in fn):
                continue
            path = root_path / fn
            if path.suffix not in _SUFFIXES:
                continue
            validate_source(path)
            validated.add(path)
    return validated


def test_testfiles() -> None:
    """Validate test metadata files used for comparing writes."""
    validated = _test_dir(TEST_EXPORT_DIR)
    validated |= _test_dir(TEST_METADATA_DIR, substring="write")
    assert len(validated) == _NUM_TEST_FILES
