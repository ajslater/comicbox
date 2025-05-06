"""MetronInfo Fields."""

from comicbox.fields.fields import StringField
from comicbox.fields.xml_fields import XmlEnumField
from comicbox.schemas.enums.maps import METRON_AGE_RATING_MAP, METRON_FORMAT_MAP
from comicbox.schemas.enums.metroninfo import (
    MetronAgeRatingEnum,
    MetronFormatEnum,
    MetronRoleEnum,
    MetronSourceEnum,
)


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
