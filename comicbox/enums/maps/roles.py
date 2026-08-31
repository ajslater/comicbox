"""
Role enum maps.

Comicbox stores one canonical role vocabulary: MetronInfo's. It is the
richest of the supported formats (42 roles against ComicInfo's 8, CoMet's 8
and ComicBookInfo's 10), and MetronInfo is the highest-priority format, so
every other format's spelling is an alias for a Metron role.

Before this map canonicalized, it was an identity union of all five
vocabularies, so a merge of a CoMet, a ComicInfo and a MetronInfo file could
carry ``colorist``, ``Colorist`` and ``Colourist`` as three separate roles for
one person. Per-format write projections (in each format's transform package)
still translate the canonical role back out to that format's spelling.

Two concepts have no Metron equivalent and are kept verbatim as comicbox
extras: ``Painter`` (which the Metron write side deliberately fans out to
Penciller + Inker + Colorist) and ``Creator`` (CoMet's generic contributor
credit).
"""

from enum import Enum
from types import MappingProxyType

from comicbox.enums.comet import CoMetRoleTagEnum
from comicbox.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.enums.comicinfo import (
    ComicInfoRoleTagEnum,
)
from comicbox.enums.generic.role import GenericRoleAliases, GenericRoleEnum
from comicbox.enums.metroninfo import (
    MetronRoleEnum,
)

# Foreign vocabularies and loose spellings, each pointing at the Metron role it
# means. Anything absent from this map falls back to titlecasing, which keeps
# unknown roles readable instead of forcing them to Other.
_FOREIGN_ROLE_MAP: MappingProxyType[Enum | str, Enum] = MappingProxyType(
    {
        # CoMet
        CoMetRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
        CoMetRoleTagEnum.COVER_DESIGNER: MetronRoleEnum.COVER,
        CoMetRoleTagEnum.CREATOR: GenericRoleEnum.CREATOR,
        CoMetRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
        CoMetRoleTagEnum.INKER: MetronRoleEnum.INKER,
        CoMetRoleTagEnum.LETTERER: MetronRoleEnum.LETTERER,
        CoMetRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
        CoMetRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
        # ComicBookInfo
        ComicBookInfoRoleEnum.ARTIST: MetronRoleEnum.ARTIST,
        ComicBookInfoRoleEnum.COLORER: MetronRoleEnum.COLORIST,
        ComicBookInfoRoleEnum.COVER_ARTIST: MetronRoleEnum.COVER,
        ComicBookInfoRoleEnum.EDITOR: MetronRoleEnum.EDITOR,
        ComicBookInfoRoleEnum.INKER: MetronRoleEnum.INKER,
        ComicBookInfoRoleEnum.LETTERER: MetronRoleEnum.LETTERER,
        ComicBookInfoRoleEnum.OTHER: MetronRoleEnum.OTHER,
        ComicBookInfoRoleEnum.PENCILLER: MetronRoleEnum.PENCILLER,
        ComicBookInfoRoleEnum.TRANSLATOR: MetronRoleEnum.TRANSLATOR,
        ComicBookInfoRoleEnum.WRITER: MetronRoleEnum.WRITER,
        # ComicInfo
        ComicInfoRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
        ComicInfoRoleTagEnum.COVER_ARTIST: MetronRoleEnum.COVER,
        ComicInfoRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
        ComicInfoRoleTagEnum.INKER: MetronRoleEnum.INKER,
        ComicInfoRoleTagEnum.LETTERER: MetronRoleEnum.LETTERER,
        ComicInfoRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
        ComicInfoRoleTagEnum.TRANSLATOR: MetronRoleEnum.TRANSLATOR,
        ComicInfoRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
        # Generic spellings
        GenericRoleEnum.AUTHOR: MetronRoleEnum.WRITER,
        GenericRoleEnum.COLOURIST: MetronRoleEnum.COLORIST,
        "penciler": MetronRoleEnum.PENCILLER,
        # Comicbox extras: no Metron equivalent, kept verbatim.
        GenericRoleEnum.CREATOR: GenericRoleEnum.CREATOR,
        GenericRoleEnum.PAINTER: GenericRoleEnum.PAINTER,
    }
)

# Loose plural and gerund spellings. Where Metron has a role of its own for the
# concept the alias names -- Breakdowns, Finishes, Plot, Script -- it wins over
# the coarser group the alias is filed under, so the distinction survives.
_ROLE_ALIAS_TARGETS: MappingProxyType[GenericRoleAliases, Enum] = MappingProxyType(
    {
        GenericRoleAliases.COLORIST: MetronRoleEnum.COLORIST,
        GenericRoleAliases.COVER: MetronRoleEnum.COVER,
        GenericRoleAliases.EDITOR: MetronRoleEnum.EDITOR,
        GenericRoleAliases.INKER: MetronRoleEnum.INKER,
        GenericRoleAliases.LETTERER: MetronRoleEnum.LETTERER,
        GenericRoleAliases.PAINTER: GenericRoleEnum.PAINTER,
        GenericRoleAliases.PENCILLER: MetronRoleEnum.PENCILLER,
        GenericRoleAliases.TRANSLATOR: MetronRoleEnum.TRANSLATOR,
        GenericRoleAliases.WRITER: MetronRoleEnum.WRITER,
    }
)
_SPECIFIC_ALIAS_ROLES: MappingProxyType[str, Enum] = MappingProxyType(
    {
        "breakdowns": MetronRoleEnum.BREAKDOWNS,
        "finishes": MetronRoleEnum.FINISHES,
        "plotter": MetronRoleEnum.PLOT,
        "scripter": MetronRoleEnum.SCRIPT,
    }
)


def _build_comicbox_role_alias_map() -> MappingProxyType[Enum | str, Enum]:
    """
    Map every known role spelling to its canonical comicbox role.

    Metron's own members are added last so an exact Metron spelling always wins
    a collision with a looser alias for the same word.
    """
    role_map: dict[Enum | str, Enum] = dict(_FOREIGN_ROLE_MAP)
    for alias_group, target in _ROLE_ALIAS_TARGETS.items():
        for alias in alias_group.value:
            role_map[alias] = _SPECIFIC_ALIAS_ROLES.get(alias, target)
    role_map.update({enum: enum for enum in MetronRoleEnum})
    return MappingProxyType(role_map)


COMICBOX_ROLE_ALIAS_MAP = _build_comicbox_role_alias_map()
