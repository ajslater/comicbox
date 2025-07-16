"""Enum Maps."""

from types import MappingProxyType

from comicbox.enums.comicbox import ReadingDirectionEnum
from comicbox.enums.generic import (
    GenericReadingDirectionEnum,
)

READING_DIRECTION_ENUM_MAP = MappingProxyType(
    {
        GenericReadingDirectionEnum.LTR: ReadingDirectionEnum.LTR,
        GenericReadingDirectionEnum.RTL: ReadingDirectionEnum.RTL,
        GenericReadingDirectionEnum.TTB: ReadingDirectionEnum.TTB,
        GenericReadingDirectionEnum.BTT: ReadingDirectionEnum.BTT,
    }
)
