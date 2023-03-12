"""Package name and version."""

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "comicbox"


def get_version():
    """Get the current installed comicbox version."""
    try:
        v = version(PACKAGE_NAME)
    except PackageNotFoundError:
        v = "dev"
    return v


VERSION = get_version()
