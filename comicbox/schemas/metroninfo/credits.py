"""Metron Credits Schemas."""

from types import MappingProxyType

from comicbox.fields.xml_fields import XmlEnumField
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.enums.metroninfo import MetronRoleEnum
from comicbox.schemas.metroninfo.identifiers import MetronIDAttrField
from comicbox.schemas.metroninfo.resource import metron_resource_field
from comicbox.schemas.xml_schemas import create_sub_tag_field, xml_list_polyfield


class MetronRoleEnumField(XmlEnumField):
    """Metron Role Enum Field."""

    ENUM = MetronRoleEnum


class MetronRoleSchema(BaseSubSchema):
    """Metron Role Schema."""

    SUPRESS_ERRORS = False  # So the union fails over

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": MetronRoleEnumField(), "@id": MetronIDAttrField()}
        )


class MetronCreditSchema(BaseSubSchema):
    """Metron Credit Schema."""

    Creator = metron_resource_field()
    Roles = create_sub_tag_field(
        "Role", xml_list_polyfield(MetronRoleSchema, MetronRoleEnumField())
    )
