"""MetronInfo Fields."""

from comicbox.enums.maps.age_rating import METRON_AGE_RATING_MAP
from comicbox.enums.maps.formats import METRON_FORMAT_MAP
from comicbox.enums.metroninfo import (
    MetronAgeRatingEnum,
    MetronFormatEnum,
    MetronRoleEnum,
    MetronSourceEnum,
)
from comicbox.fields.fields import StringField
from comicbox.fields.xml_fields import XmlEnumField


class MetronAgeRatingField(XmlEnumField):
    """Metron Age Rating Field."""

    ENUM = MetronAgeRatingEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = METRON_AGE_RATING_MAP


class MetronRoleEnumField(XmlEnumField):
    """Metron Role Enum Field."""

    ENUM = MetronRoleEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


class MetronIDAttrField(StringField):
    """Metron ID Field."""


class MetronSourceField(XmlEnumField):
    """Metron Source Field."""

    ENUM = MetronSourceEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]


class MetronFormatField(XmlEnumField):
    """Metron Series Format Field."""

    ENUM = MetronFormatEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = METRON_FORMAT_MAP
