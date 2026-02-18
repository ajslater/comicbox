"""Validate test metadata files."""

import os
from pathlib import Path

from comicbox.box.validate import validate_source
from tests.const import TEST_EXPORT_DIR, TEST_METADATA_DIR

_NUM_TEST_FILES = 16
_SUFFIXES = frozenset({"." + ext for ext in ("txt", "xml", "json", "yaml", "yml")})


def _test_dir(root_dir, substring=""):
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


def test_testfiles():
    """Validate test metadata files used for comparing writes."""
    validated = _test_dir(TEST_EXPORT_DIR)
    validated |= _test_dir(TEST_METADATA_DIR, substring="write")
    assert len(validated) == _NUM_TEST_FILES
