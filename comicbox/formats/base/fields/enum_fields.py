"""Marshmallow Enum Fields."""

from enum import Enum
from types import MappingProxyType
from typing import Any

from caseconverter import snakecase, titlecase
from loguru import logger
from marshmallow import fields
from typing_extensions import override

from comicbox.enums.comicbox import ReadingDirectionEnum
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.enums.maps.age_rating import AGE_RATING_ENUM_MAP
from comicbox.enums.maps.formats import GENERIC_FORMAT_MAP
from comicbox.enums.maps.reading_direction import READING_DIRECTION_ENUM_MAP
from comicbox.formats.base.fields.fields import StringField, TrapExceptionsMeta


class FuzzyEnumMixin:
    """Fuzzy lookup get_enum() method that allows caseless enum lookups with variations."""

    ENUM_ALIAS_MAP = MappingProxyType({})

    @staticmethod
    def get_ordered_key_variations(key: str | Enum) -> tuple[str, ...]:
        """
        Get fuzzy lookup key variations, most literal first.

        Lookups try these in order, so the exact spelling always beats a
        variation that only matches after punctuation is collapsed.
        """
        new_key = key.value if isinstance(key, Enum) else key
        new_key = new_key.lower()
        variations = (
            new_key,
            new_key.replace(" ", ""),
            snakecase(new_key).replace("_", ""),
        )
        return tuple(dict.fromkeys(variations))

    @classmethod
    def get_key_variations(cls, key: str | Enum) -> set[str]:
        """Get enum caseless slightly fuzzy lookup key variations for a key."""
        return set(cls.get_ordered_key_variations(key))

    @classmethod
    def add_enum_map_item(cls, key: str | Enum, enum: Enum, enum_map: dict) -> None:
        """Add an enum or string to the lookup table with lowercase spaceless and spaced variations."""
        key_variations = cls.get_key_variations(key)
        for key_variation in key_variations:
            enum_map[key_variation] = enum

    def get_enum_alias_map(self) -> dict:
        """Transform the ENUM_ALIAS_MAP into the enum lookup map."""
        enum_map = {}
        for key, enum in self.ENUM_ALIAS_MAP.items():
            self.add_enum_map_item(key, enum, enum_map)
        return enum_map

    def get_enum(self, value: str | Enum) -> Enum | None:
        """
        Get an enum from the fuzzy lookup map.

        The map is keyed by every variation of every known spelling, so the
        lookup must generate the same variations of the value. Lowercasing
        alone matched "Cover Artist" and "CoverArtist" to different entries
        and missed snake_case input entirely.
        """
        key: str = value.value if isinstance(value, Enum) else str(value)
        enum_map = self._enum_map  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]
        for key_variation in self.get_ordered_key_variations(key):
            if enum := enum_map.get(key_variation):
                return enum
        return None


class EnumField(FuzzyEnumMixin, fields.Enum, metaclass=TrapExceptionsMeta):
    """Fuzzy lookup Enum field that allows caseless enum lookups with variations."""

    ENUM = Enum

    def get_enum_map(self) -> dict:
        """Transform the ENUM_ALIAS_MAP into the enum lookup map and add the field enum to it as well."""
        enum_map = self.get_enum_alias_map()
        for enum in self.ENUM:
            self.add_enum_map_item(enum, enum, enum_map)
        return enum_map

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Use the enum."""
        super().__init__(self.ENUM, *args, by_value=StringField, **kwargs)
        enum_map = self.get_enum_map()
        self._enum_map = MappingProxyType(enum_map)

    @override
    def _deserialize(
        self,
        value: Enum | str,
        attr: str,
        data: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Enum:
        enum = self.get_enum(value)
        enum = enum or value
        return super()._deserialize(enum, attr, data, *args, **kwargs)

    @override
    def _serialize(
        self, value: Enum | Any | None, *args: Any, **kwargs: Any
    ) -> str | None:
        if value is None:
            return None
        enum = self.get_enum(value)
        enum = enum or value
        return super()._serialize(enum, *args, **kwargs)


class PageTypeField(EnumField):
    """ComicPageInfo Page Type Field."""

    ENUM = ComicInfoPageTypeEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


class ReadingDirectionField(EnumField):
    """Reading direction enum."""

    ENUM = ReadingDirectionEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = READING_DIRECTION_ENUM_MAP


class EnumBooleanField(EnumField):
    """An Enum Field that also accepts boolean values."""

    YES = "Yes"
    NO = "No"
    TRUTHY = frozenset(
        {
            "1",
            "true",
            "yes",
        }
    )

    def _coerce_bool(self, value: Any) -> str:
        """
        Coerce a value the enum doesn't recognize into its yes or no value.

        The enum vocabulary wins first so multi valued enums keep their extra
        members. Only unrecognized values get read as a boolean, where anything
        that isn't truthy is no.
        """
        if self.get_enum(value):
            return value
        return self.YES if str(value).lower() in self.TRUTHY else self.NO

    @override
    def _deserialize(
        self, value: Enum | str | bool, attr, data, *args, **kwargs
    ) -> Any:
        if not isinstance(value, self.ENUM):
            value = self._coerce_bool(value)
        return super()._deserialize(value, attr, data, *args, **kwargs)

    @override
    def _serialize(self, value, *args, **kwargs) -> str | None:
        if value is not None and not isinstance(value, self.ENUM):
            value = self._coerce_bool(value)
        return super()._serialize(value, *args, **kwargs)


class ComicInfoMangaEnum(Enum):
    """Manga enum for ComicInfo."""

    YES = "Yes"
    YES_RTL = "YesAndRightToLeft"
    NO = "No"


class ComicInfoMangaField(EnumBooleanField):
    """Manga field from ComicInfo."""

    ENUM = ComicInfoMangaEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]

    @override
    def _deserialize(self, value, attr, data, *args, **kwargs):
        """Match a manga value to an acceptable value."""
        if data and data.get("reading_direction") == ReadingDirectionEnum.RTL:
            reason = (
                f"Coerced manga {value} to {ComicInfoMangaEnum.YES_RTL.value}"
                "because of reading_direction"
            )
            logger.warning(reason)
            value = ComicInfoMangaEnum.YES_RTL
        return super()._deserialize(value, attr, data, *args, **kwargs)


class YesNoEnum(Enum):
    """Yes No Enum."""

    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class YesNoField(EnumBooleanField):
    """
    A yes no kind of boolean field.

    Comicbox models these tags as plain booleans, so deserialize to bool.
    The schema's Unknown means "not recorded", which is no value at all.
    """

    ENUM = YesNoEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]

    @override
    def _deserialize(self, value, attr, data, *args, **kwargs) -> Any:
        """Deserialize to a bool, or to None for the schema's Unknown."""
        enum = super()._deserialize(value, attr, data, *args, **kwargs)
        if enum == YesNoEnum.UNKNOWN:
            return None
        return enum == YesNoEnum.YES


class PrettifiedStringField(FuzzyEnumMixin, StringField):
    """A string fields that tries to match to an enum and falls back to just titlecasing."""

    ENUM_ALIAS_MAP = MappingProxyType({})

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Use the enum."""
        super().__init__(*args, **kwargs)
        self._enum_map = MappingProxyType(self.get_enum_alias_map())

    def _prettify(self, value: str) -> str:
        """Conform a value to a known enum or titlecase."""
        enum = self.get_enum(value)
        if enum:
            value = enum.value
        else:
            value = titlecase(value)
            value = value.replace("  ", " ")
        return value

    @override
    def _deserialize(self, value: Enum | str, *args: Any, **kwargs: Any) -> str:
        str_value: str = value.value if isinstance(value, Enum) else value
        str_value = super()._deserialize(str_value, *args, **kwargs)
        return self._prettify(str_value)


class OriginalFormatField(PrettifiedStringField):
    """Prettify Original Format."""

    ENUM_ALIAS_MAP = GENERIC_FORMAT_MAP


class AgeRatingField(PrettifiedStringField):
    """Prettified Age Rating."""

    ENUM_ALIAS_MAP = AGE_RATING_ENUM_MAP
