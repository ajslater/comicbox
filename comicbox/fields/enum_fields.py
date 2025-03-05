"""Marshmallow Enum Fields."""

import re
from enum import Enum
from logging import getLogger
from types import MappingProxyType

from comicfn2dict.regex import ORIGINAL_FORMAT_PATTERNS
from marshmallow import fields
from stringcase import snakecase, titlecase

from comicbox.fields.fields import StringField, TrapExceptionsMeta

_ORIGINAL_FORMAT_RE_EXP = r"^" + r"|".join(ORIGINAL_FORMAT_PATTERNS) + r"$"
_ORIGINAL_FORMAT_RE = re.compile(_ORIGINAL_FORMAT_RE_EXP, flags=re.IGNORECASE)
_CAPS_FORMATS = frozenset({"HC", "TPB"})
_PREFORMATTED_FORMATS = frozenset({"PDF Rip"})


LOG = getLogger(__name__)


class EnumField(fields.Enum, metaclass=TrapExceptionsMeta):
    """Fuzzy lookup Enum field that allows caseless enum lookups with variations."""

    ENUM = Enum
    ENUM_MAP = MappingProxyType({})

    @staticmethod
    def get_key_variations(key: str | Enum) -> set[str]:
        """Get enum caseless slightly fuzzy lookup key variations for a key."""
        new_key = key.value if isinstance(key, Enum) else key
        new_key = new_key.lower()
        key_variations = {new_key}
        key_variations.add(new_key.replace(" ", ""))
        space_case = snakecase(new_key).replace("_", "")
        key_variations.add(space_case)
        return key_variations

    @classmethod
    def _add_enum_map_item(cls, key: str | Enum, enum: Enum, enum_map: dict):
        """Add an enum or string to the lookup table with lowercase spaceless and spaced variations."""
        key_variations = cls.get_key_variations(key)
        for key_variation in key_variations:
            enum_map[key_variation] = enum

    def __init__(self, *args, **kwargs):
        """Use the enum."""
        super().__init__(self.ENUM, *args, by_value=StringField, **kwargs)
        enum_map = {}
        for key, enum in self.ENUM_MAP.items():
            self._add_enum_map_item(key, enum, enum_map)
        for enum in self.ENUM:
            self._add_enum_map_item(enum, enum, enum_map)
        self._enum_map = MappingProxyType(enum_map)

    def _get_enum(self, value):
        if isinstance(value, Enum):
            value = value.value
        return self._enum_map.get(value.lower(), value)

    def _deserialize(self, value, *args, **kwargs):
        enum = self._get_enum(value)
        return super()._deserialize(enum, *args, **kwargs)

    def _serialize(self, value, *args, **kwargs):
        enum = self._get_enum(value)
        return super()._serialize(enum, *args, **kwargs)


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


class GenericReadingDirectionEnum(Enum):
    """Long generic reading directions."""

    LTR = "LeftToRight"
    RTL = "RightToLeft"
    TTB = "TopToBottom"
    BTT = "BottomToTop"


class ReadingDirectionEnum(Enum):
    """Four reading directions."""

    LTR = "ltr"
    RTL = "rtl"
    TTB = "ttb"
    BTT = "btt"


class ReadingDirectionField(EnumField):
    """Reading direction enum."""

    ENUM = ReadingDirectionEnum
    ENUM_MAP = MappingProxyType(
        {
            GenericReadingDirectionEnum.LTR: ReadingDirectionEnum.LTR,
            GenericReadingDirectionEnum.RTL: ReadingDirectionEnum.RTL,
            GenericReadingDirectionEnum.TTB: ReadingDirectionEnum.TTB,
            GenericReadingDirectionEnum.BTT: ReadingDirectionEnum.BTT,
        }
    )


class EnumBooleanField(EnumField):
    """An Enum Field that also accepts boolean values."""

    TRUTHY = frozenset({True, "1", "true"})

    def _deserialize(self, value, *args, **kwargs):
        result = super()._deserialize(value, *args, **kwargs)
        if not isinstance(result, self.ENUM) and value in self.TRUTHY:
            result = super()._deserialize("yes", *args, **kwargs)
        return result

    def _serialize(self, value, *args, **kwargs):
        result = super()._serialize(value, *args, **kwargs)
        if not isinstance(result, self.ENUM) and value in self.TRUTHY:
            result = super()._serialize("yes", *args, **kwargs)
        return result


class ComicInfoMangaEnum(Enum):
    """Manga enum for ComicInfo."""

    YES = "Yes"
    YES_RTL = "YesAndRightToLeft"
    NO = "No"


class ComicInfoMangaField(EnumBooleanField):
    """Manga field from ComicInfo."""

    ENUM = ComicInfoMangaEnum

    def _deserialize(self, value, attr, data, *args, **kwargs):
        """Match a manga value to an acceptable value."""
        if data.get("reading_direction") == ReadingDirectionEnum.RTL:
            LOG.warning(
                f"Coerced manga {value} to {ComicInfoMangaEnum.YES_RTL.value}"
                "because of reading_direction"
            )
            value = ComicInfoMangaEnum.YES_RTL
        return super()._deserialize(value, attr, data, *args, **kwargs)


class YesNoEnum(Enum):
    """Yes No Enum."""

    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class YesNoField(EnumBooleanField):
    """A yes no kind of boolean field."""

    ENUM = YesNoEnum


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
