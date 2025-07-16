"""Role enum maps."""

from types import MappingProxyType

from comicbox.enums.comet import CoMetRoleTagEnum
from comicbox.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.enums.comicinfo import (
    ComicInfoRoleTagEnum,
)
from comicbox.enums.generic.role import GenericRoleEnum
from comicbox.enums.metroninfo import (
    MetronRoleEnum,
)

COMICBOX_ROLE_ALIAS_MAP = MappingProxyType(
    {
        **{enum: enum for enum in CoMetRoleTagEnum},
        **{enum: enum for enum in ComicBookInfoRoleEnum},
        **{enum: enum for enum in ComicInfoRoleTagEnum},
        **{enum: enum for enum in MetronRoleEnum},
        **{enum: enum for enum in GenericRoleEnum},
    }
)
