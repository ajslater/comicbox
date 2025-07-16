"""Comicbox Schema Enums."""

from enum import Enum
from sys import maxsize
from types import MappingProxyType


class ReadingDirectionEnum(Enum):
    """Four reading directions."""

    RTL = "rtl"
    LTR = "ltr"
    TTB = "ttb"
    BTT = "btt"


class IdSources(Enum):
    """Comic Database Namespace Identifiers."""

    # Comic DBs
    METRON = "metron"
    COMICVINE = "comicvine"
    GCD = "grandcomicsdatabase"
    LCG = "leagueofcomicgeeks"
    MARVEL = "marvel"
    PANELSYNDICATE = "panelsyndicate"
    # Manga DBs
    ANILIST = "anilist"
    KITSU = "kitsu"
    MANGADEX = "mangadex"
    MANGAUPDATES = "mangaupdates"
    MYANIMELIST = "myanimelist"
    # GTINs
    GTIN = "gtin"
    ISBN = "isbn"
    UPC = "upc"
    ASIN = "asin"
    COMIXOLOGY = "comixology"


# Non standard
class AlternateIdSources(Enum):
    """Alternate ID_SOURCE Names."""

    CVDB_ALTERNATE = "cvdb"
    CMXDB_ALTERNATE = "cmxdb"


class FileTypeEnum(Enum):
    """File types."""

    CBZ = "CBZ"
    CBR = "CBR"
    CB7 = "CB7"
    CBT = "CBT"
    PDF = "PDF"


_ID_SOURCES_RANK: MappingProxyType[str, int] = MappingProxyType(
    {enum.value: index for index, enum in enumerate(IdSources)}
)


def compare_identifier_source(
    id_source_a: IdSources | str | None, id_source_b: IdSources | str | None
):
    """Compare identifier sources by string."""
    if isinstance(id_source_a, IdSources):
        id_source_a = id_source_a.value
    else:
        id_source_a = id_source_a.lower() if id_source_a else ""

    if isinstance(id_source_b, IdSources):
        id_source_b = id_source_b.value
    else:
        id_source_b = id_source_b.lower() if id_source_b else ""

    id_source_a_rank = _ID_SOURCES_RANK.get(id_source_a, maxsize)
    id_source_b_rank = _ID_SOURCES_RANK.get(id_source_b, maxsize)

    return id_source_a_rank > id_source_b_rank
