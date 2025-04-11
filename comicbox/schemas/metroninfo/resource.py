"""Metron Resource Schemas."""

from types import MappingProxyType

from marshmallow.fields import Field

from comicbox.fields.collection_fields import ListField
from comicbox.fields.fields import StringField
from comicbox.fields.xml_fields import xml_list_polyfield, xml_polyfield
from comicbox.schemas.metroninfo.identifiers import MetronIDAttrField
from comicbox.schemas.xml_schemas import XmlSubSchema


class MetronResourceSchema(XmlSubSchema):
    """Metron Resource Schema."""

    SUPRESS_ERRORS = False  # So the union fails over

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": StringField(required=True), "@id": MetronIDAttrField()}
        )


def metron_resource_field() -> Field:
    """Get metron union resource and simple text field."""
    return xml_polyfield(MetronResourceSchema, StringField())


def metron_resource_list_field(**kwargs) -> ListField:
    """Get metron union resource and simple text field."""
    return xml_list_polyfield(MetronResourceSchema, StringField(), **kwargs)
