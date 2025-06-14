"""Metron Credits Schemas."""

from types import MappingProxyType

from comicbox.fields.metroninfo import MetronIDAttrField, MetronRoleEnumField
from comicbox.fields.xml_fields import create_sub_tag_field, xml_list_polyfield
from comicbox.schemas.metroninfo.resource import metron_resource_field
from comicbox.schemas.xml_schemas import XmlSubSchema


class MetronRoleSchema(XmlSubSchema):
    """Metron Role Schema."""

    # So the union fails over
    SUPRESS_ERRORS: bool = False

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": MetronRoleEnumField(), "@id": MetronIDAttrField()}
        )


class MetronCreditSchema(XmlSubSchema):
    """Metron Credit Schema."""

    Creator = metron_resource_field()
    Roles = create_sub_tag_field(
        "Role", xml_list_polyfield(MetronRoleSchema, MetronRoleEnumField())
    )
