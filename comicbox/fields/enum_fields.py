"""Marshmallow Enum Fields."""

from enum import Enum
from logging import getLogger
from types import MappingProxyType

from marshmallow import fields
from stringcase import snakecase, titlecase
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta
from comicbox.schemas.enums.age_rating import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)
from comicbox.schemas.enums.comicinfo import ComicInfoAgeRatingEnum
from comicbox.schemas.enums.metroninfo import (
    GenericFormatEnum,
    MetronAgeRatingEnum,
    MetronFormatEnum,
)

LOG = getLogger(__name__)


class FuzzyEnumMixin:
    """Fuzzy lookup get_enum() method that allows caseless enum lookups with variations."""

    ENUM_ALIAS_MAP = MappingProxyType({})

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
    def add_enum_map_item(cls, key: str | Enum, enum: Enum, enum_map: dict):
        """Add an enum or string to the lookup table with lowercase spaceless and spaced variations."""
        key_variations = cls.get_key_variations(key)
        for key_variation in key_variations:
            enum_map[key_variation] = enum

    def init_enum_map(self):
        """Transform the ENUM_ALIAS_MAP into the enum lookup map."""
        enum_map = {}
        for key, enum in self.ENUM_ALIAS_MAP.items():
            self.add_enum_map_item(key, enum, enum_map)
        self._enum_map = MappingProxyType(enum_map)  # pyright: ignore[reportUninitializedInstanceVariable]

    def get_enum(self, value) -> Enum | None:
        """Get an enum from the fuzzy lookup map."""
        if isinstance(value, Enum):
            value = value.value
        return self._enum_map.get(value.lower())


class EnumField(FuzzyEnumMixin, fields.Enum, metaclass=TrapExceptionsMeta):
    """Fuzzy lookup Enum field that allows caseless enum lookups with variations."""

    ENUM = Enum

    @override
    def init_enum_map(self):
        """Transform the ENUM_ALIAS_MAP into the enum lookup map and add the field enum to it as well."""
        super().init_enum_map()
        enum_map = dict(self._enum_map)
        for enum in self.ENUM:
            self.add_enum_map_item(enum, enum, enum_map)
        self._enum_map = MappingProxyType(enum_map)

    def __init__(self, *args, **kwargs):
        """Use the enum."""
        super().__init__(self.ENUM, *args, by_value=StringField, **kwargs)
        self.init_enum_map()

    @override
    def _deserialize(self, value, *args, **kwargs):
        enum = self.get_enum(value)
        enum = enum if enum else value
        return super()._deserialize(enum, *args, **kwargs)

    @override
    def _serialize(self, value, *args, **kwargs):
        enum = self.get_enum(value)
        enum = enum if enum else value
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

    ENUM = PageTypeEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


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

    ENUM = ReadingDirectionEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = MappingProxyType(
        {
            GenericReadingDirectionEnum.LTR: ReadingDirectionEnum.LTR,
            GenericReadingDirectionEnum.RTL: ReadingDirectionEnum.RTL,
            GenericReadingDirectionEnum.TTB: ReadingDirectionEnum.TTB,
            GenericReadingDirectionEnum.BTT: ReadingDirectionEnum.BTT,
        }
    )


class EnumBooleanField(EnumField):
    """An Enum Field that also accepts boolean values."""

    YES = "Yes"
    TRUTHY = frozenset({True, "1", "true", "True"})

    @override
    def _deserialize(self, value, *args, **kwargs):
        result = super()._deserialize(value, *args, **kwargs)
        if not isinstance(result, self.ENUM) and value in self.TRUTHY:
            result = super()._deserialize(self.YES, *args, **kwargs)
        return result

    @override
    def _serialize(self, value, *args, **kwargs):
        result = super()._serialize(value, *args, **kwargs)
        if not isinstance(result, self.ENUM) and value in self.TRUTHY:
            result = super()._serialize(self.YES, *args, **kwargs)
        return result


class ComicInfoMangaEnum(Enum):
    """Manga enum for ComicInfo."""

    YES_RTL = "YesAndRightToLeft"
    NO = "No"


class ComicInfoMangaField(EnumBooleanField):
    """Manga field from ComicInfo."""

    ENUM = ComicInfoMangaEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]

    @override
    def _deserialize(self, value, attr, data, *args, **kwargs):
        """Match a manga value to an acceptable value."""
        if data.get("reading_direction") == ReadingDirectionEnum.RTL:
            reason = (
                f"Coerced manga {value} to {ComicInfoMangaEnum.YES_RTL.value}"
                "because of reading_direction"
            )
            LOG.warning(reason)
            value = ComicInfoMangaEnum.YES_RTL
        return super()._deserialize(value, attr, data, *args, **kwargs)


class YesNoEnum(Enum):
    """Yes No Enum."""

    NO = "No"
    UNKNOWN = "Unknown"


class YesNoField(EnumBooleanField):
    """A yes no kind of boolean field."""

    ENUM = YesNoEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


class PrettifiedStringField(FuzzyEnumMixin, StringField):
    """A string fields that tries to match to an enum and falls back to just titlecasing."""

    ENUM_ALIAS_MAP = MappingProxyType({})

    def __init__(self, *args, **kwargs):
        """Use the enum."""
        super().__init__(*args, **kwargs)
        self.init_enum_map()

    def _prettify(self, value) -> str:
        """Conform a value to a known enum or titlecase."""
        enum = self.get_enum(value)
        if enum:
            value = enum.value
        else:
            value = titlecase(value)
            value = value.replace("  ", " ")
        return value

    @override
    def _deserialize(self, value, *args, **kwargs):
        value = super()._deserialize(value, *args, **kwargs)
        return self._prettify(value)


ORIGINAL_FORMAT_ENUM_MAP = MappingProxyType(
    {
        **{enum: enum for enum in GenericFormatEnum},
        **{enum: enum for enum in MetronFormatEnum},
    }
)


class OriginalFormatField(PrettifiedStringField):
    """Prettify Original Format."""

    ENUM_ALIAS_MAP = ORIGINAL_FORMAT_ENUM_MAP


AGE_RATING_ENUM_MAP = MappingProxyType(
    {
        **{enum: enum for enum in GenericAgeRatingEnum},
        **{enum: enum for enum in DCAgeRatingEnum},
        **{enum: enum for enum in MarvelAgeRatingEnum},
        **{enum: enum for enum in ComicInfoAgeRatingEnum},
        **{enum: enum for enum in MetronAgeRatingEnum},
    }
)


class AgeRatingField(PrettifiedStringField):
    """Prettified Age Rating."""

    ENUM_ALIAS_MAP = AGE_RATING_ENUM_MAP
