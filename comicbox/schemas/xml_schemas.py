"""XML Metadata parser superclass."""

from abc import ABC
from types import MappingProxyType

import xmltodict
from marshmallow.fields import Constant

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
