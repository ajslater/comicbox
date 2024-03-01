"""XML Metadata parser superclass."""

from abc import ABC
from types import MappingProxyType

import xmltodict
from marshmallow.fields import Constant, Nested
from marshmallow_union import Union

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
        cleaned_s = StringField().deserialize(s)
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
                # "@xmlns:comicbox": Constant("https://github.com/ajslater/comicbox/"),
                "@xmlns:xsd": Constant("http://www.w3.org/2001/XMLSchema"),
                "@xmlns:xsi": Constant("http://www.w3.org/2001/XMLSchema-instance"),
                XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://github.com/ajslater/comicbox/blob/main/schemas/comicbox.xsd"
                ),
            }
        )


class XmlSchema(BaseSchema, ABC):
    """Xml Schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = XmlRenderModule


def create_text_schema(field):
    """Create a text schema with a designated field type."""
    schema_name = field.__class__.__name__ + "TextSchema"
    schema_class = type(schema_name, (BaseSubSchema,), {})
    schema_class.Meta = type(
        "Meta", (BaseSubSchema.Meta,), {"include": {"#text": field}}
    )
    return schema_class


def get_xml_poly_text_field(
    field, collection_field=None, schema_class=None, many=False
):
    """Get a union field of xml list variations."""
    fields = []
    if not schema_class:
        schema_class = create_text_schema(field)
    fields.append(Nested(schema_class, many=many))
    if collection_field:
        fields.append(collection_field)
    if field:
        fields.append(field)
    return Union(fields)
