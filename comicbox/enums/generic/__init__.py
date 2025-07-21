"""Generic enums shared between schemas."""

from enum import Enum

from comicbox.enums.generic.age_rating import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)

__all__ = (
    "DCAgeRatingEnum",
    "GenericAgeRatingEnum",
    "GenericFormatEnum",
    "GenericReadingDirectionEnum",
    "MarvelAgeRatingEnum",
)


class GenericReadingDirectionEnum(Enum):
    """Long generic reading directions."""

    LTR = "LeftToRight"
    RTL = "RightToLeft"
    TTB = "TopToBottom"
    BTT = "BottomToTop"


class GenericFormatEnum(Enum):
    """Generic Format Values."""

    ANTHOLOGY = "Anthology"
    ANNOTATION = "Annotation"
    BOX_SET = "Box Set"
    DIGITAL = "Digital"
    DIRECTOR_S_CUT = "Director's Cut"
    GIANT_SIZED = "Giant Sized"
    GRAPHIC_NOVEL = "Graphic Novel"
    HARD_COVER = "Hardcover"
    HD_UPSCALED = "HD Upscaled"
    KING_SIZED = "King Sized"
    MAGAZINE = "Magazine"
    MANGA = "Manga"
    ONE_SHOT = "One-Shot"
    PDF_RIP = "PDF Rip"
    PREVIEW = "Preview"
    PROLOGUE = "Prologue"
    SCANLATION = "Scanlation"
    SCRIPT = "Script"
    TRADE_PAPERBACK = "Trade Paperback"
    WEB_COMIC = "Web Comic"
    WEB_RIP = "Web Rip"
