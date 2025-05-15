"""Test getting pages."""

from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from comicbox.box import Comicbox
from tests.const import TEST_FILES_DIR

FIXTURES = MappingProxyType(
    {
        "test_pdf.pdf": datetime(2025, 4, 11, 3, 8, 24, 119570, tzinfo=timezone.utc),
        "Captain Science #001-cix-cbi.cbr": datetime(
            2025, 5, 6, 1, 50, 37, 83614, tzinfo=timezone.utc
        ),
        "Captain Science #001.cbz": datetime(
            2025, 4, 10, 20, 8, 24, tzinfo=timezone.utc
        ),
        "Captain Science #001 (1950) The Beginning - multi.cbz": datetime(
            2025, 4, 9, 14, 41, 6, tzinfo=timezone.utc
        ),
        "empty.cbz": None,
    }
)


@pytest.mark.parametrize("fn", FIXTURES)
def test_get_mtime(fn):
    """Test metadata mtime."""
    path = TEST_FILES_DIR / fn
    with Comicbox(path) as car:
        mtime = car.get_metadata_mtime()
    test_mtime = FIXTURES[fn]
    assert test_mtime == mtime
