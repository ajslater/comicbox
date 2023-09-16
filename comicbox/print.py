"""Print phases enum."""
from enum import Enum


class PrintPhases(Enum):
    """Items that can be printed."""

    VERSION = "v"
    FILE_TYPE = "t"
    FILE_NAMES = "n"

    # Metadata
    SOURCE = "s"
    PARSED = "p"
    LOADED = "l"
    LOADED_SYNTHED = "y"
    COMPUTED = "c"
    METADATA = "m"
