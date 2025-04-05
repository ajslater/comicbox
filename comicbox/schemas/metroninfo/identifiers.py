"""Metron @id field."""

from types import MappingProxyType

from comicbox.fields.fields import StringField
from comicbox.fields.xml_fields import (
    XmlBooleanAttributeField,
    XmlEnumField,
    XmlStringField,
)
from comicbox.schemas.enums.metroninfo import MetronSourceEnum
from comicbox.schemas.xml_schemas import XmlSubSchema


class MetronIDAttrField(StringField):
    """Metron ID Field."""


class MetronIdentifiedNameSchema(XmlSubSchema):
    """Metron Schema with a Name and @id."""

    Name = XmlStringField(required=True)

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


class MetronSourceField(XmlEnumField):
    """Metron Source Field."""

    ENUM = MetronSourceEnum


class MetronPrimaryAttrSchema(XmlSubSchema):
    """Metron URL Schema."""

    class Meta(XmlSubSchema.Meta):
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


class MetronGTINSchema(XmlSubSchema):
    """Metron GTIN Schema."""

    ISBN = XmlStringField()
    UPC = XmlStringField()
