"""Metron @id field."""

from types import MappingProxyType

from comicbox.fields.fields import StringField
from comicbox.fields.metroninfo import MetronIDAttrField, MetronSourceField
from comicbox.fields.xml_fields import XmlBooleanAttributeField, XmlStringField
from comicbox.schemas.xml_schemas import XmlSubSchema


class MetronIdentifiedNameSchema(XmlSubSchema):
    """Metron Schema with a Name and @id."""

    Name = XmlStringField(required=True)

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


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

    # So the union fails over
    SUPRESS_ERRORS: bool = False


class MetronGTINSchema(XmlSubSchema):
    """Metron GTIN Schema."""

    ISBN = XmlStringField()
    UPC = XmlStringField()
