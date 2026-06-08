"""
Shared test utilities.

Split from the former monolithic ``tests/util.py`` into focused modules:

* :mod:`tests.util.tmp` — temp-directory lifecycle helpers.
* :mod:`tests.util.diff` — diff-based assertion helpers.
* :mod:`tests.util.compare` — file/string comparison that ignores volatile
  metadata fields.
* :mod:`tests.util.metadata` — metadata read/compare and write-metadata
  factories.
* :mod:`tests.util.parser` — the generic ``TestParser`` round-trip harness.

The names below are re-exported so existing ``from tests.util import ...``
call sites keep working unchanged.
"""

from .compare import compare_export
from .diff import assert_diff, assert_diff_strings
from .metadata import create_write_dict, create_write_metadata, read_metadata
from .parser import TestParser
from .tmp import get_tmp_dir, my_cleanup, my_setup

__all__ = (
    "TestParser",
    "assert_diff",
    "assert_diff_strings",
    "compare_export",
    "create_write_dict",
    "create_write_metadata",
    "get_tmp_dir",
    "my_cleanup",
    "my_setup",
    "read_metadata",
)
