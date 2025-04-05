"""Metron @id field."""

from types import MappingProxyType

from comicbox.fields.fields import StringField
from comicbox.fields.xml_fields import (
    XmlBooleanAttributeField,
    XmlEnumField,
    XmlStringField,
)
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.enums.metroninfo import MetronSourceEnum


class MetronIDAttrField(StringField):
    """Metron ID Field."""


class MetronIdentifiedNameSchema(BaseSubSchema):
    """Metron Schema with a Name and @id."""

    Name = XmlStringField(required=True)

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


class MetronSourceField(XmlEnumField):
    """Metron Source Field."""

    ENUM = MetronSourceEnum


class MetronPrimaryAttrSchema(BaseSubSchema):
    """Metron URL Schema."""

    class Meta(BaseSubSchema.Meta):
        """Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(required=True),
                "@primary": XmlBooleanAttributeField(),
            }
        )


class MetronIDSchema(MetronPrimaryAttrSchema):
    """Metron ID Schema."""

    class Meta(MetronPrimaryAttrSchema.Meta):
        """Attributes."""

        include = MappingProxyType(
            {
                "@source": MetronSourceField(required=True),
            }
        )


class MetronURLSchema(MetronPrimaryAttrSchema):
    """Metron URL Schema."""

    SUPRESS_ERRORS = False  # So the union fails over


class MetronGTINSchema(BaseSubSchema):
    """Metron GTIN Schema."""

    ISBN = XmlStringField()
    UPC = XmlStringField()
