"""Package name and version."""

import sys
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "comicbox"


def get_version():
    """Get the current installed comicbox version."""
    v = "dev"
    if "pytest" not in sys.modules:
        with suppress(PackageNotFoundError):
            v = version(PACKAGE_NAME)
    return v


VERSION = get_version()
DEFAULT_TAGGER = f"{PACKAGE_NAME} {VERSION}"
