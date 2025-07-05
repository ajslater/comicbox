"""Comicbox Schema Enums."""

from enum import Enum


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
