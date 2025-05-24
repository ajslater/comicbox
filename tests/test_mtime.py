"""Test getting pages."""

from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from comicbox.box import Comicbox
from tests.const import TEST_FILES_DIR


def _get_stat_mtime(fn):
    return datetime.fromtimestamp(
        (TEST_FILES_DIR / fn).stat().st_mtime, tz=timezone.utc
    )


FIXTURES = MappingProxyType(
    {
        "test_pdf.pdf": _get_stat_mtime("test_pdf.pdf"),
        "Captain Science #001-cix-cbi.cbr": _get_stat_mtime(
            "Captain Science #001-cix-cbi.cbr"
        ),
        "Captain Science #001.cbz": datetime(
            2025, 5, 22, 15, 33, 00, tzinfo=timezone.utc
        ),
        "Captain Science #001 (1950) The Beginning - multi.cbz": datetime(
            2025, 5, 23, 17, 49, 28, tzinfo=timezone.utc
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
