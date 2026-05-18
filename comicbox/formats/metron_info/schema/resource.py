"""Metron Resource Schemas."""

from types import MappingProxyType
from typing import Any

from marshmallow.fields import Field

from comicbox.formats.base.fields.collection_fields import ListField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.metroninfo import MetronIDAttrField
from comicbox.formats.base.fields.xml_fields import xml_list_polyfield, xml_polyfield
from comicbox.formats.base.schemas.xml_schemas import XmlSubSchema


class MetronResourceSchema(XmlSubSchema):
    """Metron Resource Schema."""

    # So the union fails over
    SUPPRESS_ERRORS: bool = False

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": StringField(required=True), "@id": MetronIDAttrField()}
        )


def metron_resource_field() -> Field:
    """Get metron union resource and simple text field."""
    return xml_polyfield(MetronResourceSchema, StringField())


def metron_resource_list_field(**kwargs: Any) -> ListField:
    """Get metron union resource and simple text field."""
    return xml_list_polyfield(MetronResourceSchema, StringField(), **kwargs)
