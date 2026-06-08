"""Package name and version."""

import sys
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "comicbox"


def get_version() -> str:
    """Get the current installed comicbox version."""
    v = "dev"
    if "pytest" not in sys.modules:
        with suppress(PackageNotFoundError):
            v = version(PACKAGE_NAME)
    return v


VERSION = get_version()
# Metadata provenance stamp (tagger field + ComicTagger-style notes). Space
# delimiter matches the ComicTagger convention the notes parser round-trips.
DEFAULT_TAGGER = f"{PACKAGE_NAME} {VERSION}"
# HTTP User-Agent for online API clients (simyan, mokkari). Slash delimiter is
# the RFC 9110 product-token convention, distinct from DEFAULT_TAGGER on purpose.
USER_AGENT = f"{PACKAGE_NAME}/{VERSION}"
