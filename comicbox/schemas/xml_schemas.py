"""XML Metadata parser superclass."""

from abc import ABC
from types import MappingProxyType

import xmltodict
from marshmallow.fields import Constant, Field, Nested
from marshmallow.schema import Schema
from marshmallow_union import Union

from comicbox.fields.collection_fields import ListField
from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSchema, BaseSubSchema


class XmlRenderModule:
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to XML string."""
        return xmltodict.unparse(
            obj, *args, pretty=True, short_empty_elements=True, **kwargs
        )

    @staticmethod
    def loads(s: bytes | str, *args, **kwargs):
        """Load XML string into a dict."""
        cleaned_s: str | None = StringField().deserialize(s)  # type:ignore[reportAssignmentType]
        if cleaned_s:
            return xmltodict.parse(cleaned_s, *args, **kwargs)
        return None


class XmlSubSchema(BaseSubSchema, ABC):
    """XML Sub Schema customizations."""

    class Meta(BaseSubSchema.Meta):
        """Schema Options."""

        XSI_SCHEMA_LOCATION_KEY = "@xsi:schemaLocation"

        include = MappingProxyType(
            {
                "@xmlns:xsd": Constant("http://www.w3.org/2001/XMLSchema"),
                "@xmlns:xsi": Constant("http://www.w3.org/2001/XMLSchema-instance"),
                XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.xsd"
                ),
            }
        )
        render_module = XmlRenderModule


class XmlSchema(BaseSchema, ABC):
    """Xml Schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = XmlRenderModule


def create_sub_tag_field(
    sub_tag: str,
    field: Field,
) -> Nested:
    """Create a nested single schema, common to xml schemas."""
    sub_tag_schema_name = sub_tag + "Schema"
    sub_tag_schema_class = type(sub_tag_schema_name, (BaseSubSchema,), {sub_tag: field})
    return Nested(sub_tag_schema_class)


def xml_polyfield(schema_class: type[Schema], field: Field) -> Union:
    """Get a Union of nested schemas and fields."""
    return Union(
        [
            # First field is the unparse type
            Nested(schema_class),
            field,
        ]
    )


def xml_list_polyfield(
    schema_class: type[Schema],
    field: Field,
    sort_keys: tuple[str, ...] = ("#text",),
    **kwargs,
) -> ListField:
    """Get a List of unions."""
    union_field = xml_polyfield(schema_class, field)
    return ListField(union_field, sort_keys=sort_keys, **kwargs)
