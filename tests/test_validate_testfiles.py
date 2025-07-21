"""Validate test metadata files."""

import os
from pathlib import Path

from tests.const import TEST_EXPORT_DIR, TEST_METADATA_DIR
from tests.validate.validate import guess_format, validate_path

_NUM_TEST_FILES = 16


def _test_dir(root_dir, substring=""):
    validated = set()
    for root, _, fns in os.walk(root_dir):
        root_path = Path(root)
        for fn in fns:
            if substring and substring not in fn:
                continue
            path = root_path / fn
            try:
                fmt = guess_format(path)
            except ValueError:
                continue
            validate_path(path, fmt)
            validated.add(path)
    return validated


def test_testfiles():
    """Validate test metadata files used for comparing writes."""
    validated = _test_dir(TEST_EXPORT_DIR)
    validated |= _test_dir(TEST_METADATA_DIR, substring="write")
    assert len(validated) == _NUM_TEST_FILES
