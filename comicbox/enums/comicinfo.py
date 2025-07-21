"""ComicInfo.xml Enums."""

from enum import Enum


class ComicInfoRoleTagEnum(Enum):
    """ComicInfo Role tags."""

    COLORIST = "Colorist"
    COVER_ARTIST = "CoverArtist"
    EDITOR = "Editor"
    INKER = "Inker"
    LETTERER = "Letterer"
    PENCILLER = "Penciller"
    TRANSLATOR = "Translator"
    WRITER = "Writer"


class ComicInfoAgeRatingEnum(Enum):
    """ComicInfo Age Ratings."""

    UNKNOWN = "Unknown"
    A_18_PLUS = "Adults Only 18+"
    EARLY_CHILDHOOD = "Early Childhood"
    EVERYONE = "Everyone"
    E_10_PLUS = "Everyone 10+"
    G = "G"
    KIDS_TO_ADULTS = "Kids to Adults"
    M = "M"
    MA_15_PLUS = "MA15+"
    MA_17_PLUS = "Mature 17+"
    PG = "PG"
    R_18_PLUS = "R18+"
    PENDING = "Rating Pending"
    TEEN = "Teen"
    X_18_PLUS = "X18+"


class ComicInfoPageTypeEnum(Enum):
    """ComicPageInfo Page Types."""

    FRONT_COVER = "FrontCover"
    INNER_COVER = "InnerCover"
    ROUNDUP = "Roundup"
    STORY = "Story"
    ADVERTISEMENT = "Advertisement"
    EDITORIAL = "Editorial"
    LETTERS = "Letters"
    PREVIEW = "Preview"
    BACK_COVER = "BackCover"
    OTHER = "Other"
    DELETED = "Deleted"
