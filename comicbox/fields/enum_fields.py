"""Marshmallow Enum Fields."""

import re
from enum import Enum
from logging import getLogger
from types import MappingProxyType

from comicfn2dict.regex import ORIGINAL_FORMAT_PATTERNS
from marshmallow import fields
from stringcase import titlecase

from comicbox.fields.fields import StringField, TrapExceptionsMeta
from comicbox.fields.number_fields import BooleanField

_ORIGINAL_FORMAT_RE_EXP = r"^" + r"|".join(ORIGINAL_FORMAT_PATTERNS) + r"$"
_ORIGINAL_FORMAT_RE = re.compile(_ORIGINAL_FORMAT_RE_EXP, flags=re.IGNORECASE)
_CAPS_FORMATS = frozenset({"HC", "TPB"})
_PREFORMATTED_FORMATS = frozenset({"PDF Rip"})


LOG = getLogger(__name__)


class EnumField(fields.Enum, metaclass=TrapExceptionsMeta):
    """Durable enum field."""

    ENUM = Enum

    def __init__(self, *args, **kwargs):
        """Use the enum."""
        super().__init__(self.ENUM, *args, by_value=StringField, **kwargs)

    def _deserialize(self, value, *args, **kwargs):
        if isinstance(value, Enum):
            """Because by_value is StringField, convert to string first."""
            value = value.value
        return super()._deserialize(value, *args, **kwargs)


class PageTypeEnum(Enum):
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


class PageTypeField(EnumField):
    """ComicPageInfo Page Type Field."""

    ENUM = PageTypeEnum


class ReadingDirectionEnum(Enum):
    """Four reading directions."""

    LTR = "ltr"
    RTL = "rtl"
    TTB = "ttb"
    BTT = "btt"


class ReadingDirectionField(EnumField):
    """Reading direction enum."""

    ENUM = ReadingDirectionEnum

    def _deserialize(self, value, *args, **kwargs):
        """Match a reading direction to an acceptable value."""
        if isinstance(value, str):
            value = value.lower()
        return super()._deserialize(value, *args, **kwargs)


class MangaEnum(Enum):
    """Manga enum for ComicInfo."""

    YES = "Yes"
    YES_RTL = "YesAndRightToLeft"
    NO = "No"


class MangaField(EnumField):
    """Manga field from ComicInfo."""

    ENUM = MangaEnum

    def _deserialize(self, value, attr, data, *args, **kwargs):
        """Match a manga value to an acceptable value."""
        if data.get("reading_direction") == ReadingDirectionEnum.RTL:
            LOG.warning(
                f"Coerced manga {value} to {MangaEnum.YES_RTL.value}"
                "because of reading_direction"
            )
            value = MangaEnum.YES_RTL
        elif isinstance(value, str):
            value = value.strip()
            if value.lower() == MangaEnum.YES_RTL.value.lower():
                value = MangaEnum.YES_RTL
            else:
                value = value.capitalize()
        return super()._deserialize(value, attr, data, *args, **kwargs)


class AgeRatingEnum(Enum):
    """Age Ratings."""

    A_18_PLUS = "Adults Only 18+"
    EARLY_CHILDHOOD = "Early Childhood"
    EVERYONE = "Everyone"
    E_10_PLUS = "Everyone 10+"
    G = "G"
    KIDS_TO_ADULTS = "Kids to Adults"
    M = "M"
    MATURE = "Mature"
    MA_15_PLUS = "MA15+"
    MA_17_PLUS = "Mature 17+"
    PG = "PG"
    R_18_PLUS = "R18+"
    PENDING = "Rating Pending"
    TEEN = "Teen"
    TEEN_PLUS = "Teen Plus"
    X_18_PLUS = "X18+"


_AGE_RATING_MAP = MappingProxyType(
    {age_rating.value.lower(): age_rating.value for age_rating in AgeRatingEnum}
)


class AgeRatingField(StringField):
    """
    Overly lenient age rating field.

    *Not* an Enum. Accept any string.
    Age ratings are so messy, I think it hurts to be restrictive.
    """

    def _deserialize(self, value, *args, **kwargs):
        """Prettify if possible, but allow anything."""
        value = super()._deserialize(value, *args, **kwargs)
        if value and (pretty_value := _AGE_RATING_MAP.get(value.lower())):
            value = pretty_value
        return value


class YesNoEnum(Enum):
    """Yes No Enum."""

    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class YesNoField(BooleanField):
    """A yes no kind of boolean field."""

    _UNKNOWN_LOWER = YesNoEnum.UNKNOWN.value.lower()

    def _deserialize(self, value, *args, **kwargs) -> bool | None:  # type: ignore[reportIncompatibleMethodOverride]
        """Accept any boolean value."""
        if isinstance(value, str) and value.lower() == self._UNKNOWN_LOWER:
            return None
        return super()._deserialize(value, *args, **kwargs)

    def _serialize(self, value, *_args, **_kwargs) -> str:  # type: ignore[reportIncompatibleMethodOverride]
        """Serialize to specific values."""
        if value is None:
            return YesNoEnum.UNKNOWN.value
        if value:
            return YesNoEnum.YES.value
        return YesNoEnum.NO.value


class OriginalFormatField(StringField):
    """Prettify Original Format."""

    def _deserialize(self, value, *args, **kwargs):
        """Prettify Original Format if it's known."""
        value = super()._deserialize(value, *args, **kwargs)
        if not value or not _ORIGINAL_FORMAT_RE.search(value):
            return value
        value_upper = value.upper()
        for preformatted_value in _PREFORMATTED_FORMATS:
            if value_upper == preformatted_value.upper():
                value = preformatted_value
                break
        else:
            if value_upper in _CAPS_FORMATS:
                value = value_upper
            else:
                value = titlecase(value)
                value = value.replace("  ", " ")
        return value
