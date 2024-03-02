"""Print phases enum."""

from enum import Enum


class PrintPhases(Enum):
    """Items that can be printed."""

    VERSION = "v"
    FILE_TYPE = "t"
    FILE_NAMES = "f"

    # Metadata
    SOURCE = "s"
    LOADED = "l"
    NORMALIZED = "n"
    MERGED = "m"
    COMPUTED = "c"
    METADATA = "d"
