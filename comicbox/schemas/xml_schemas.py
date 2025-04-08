"""XML Metadata parser superclass."""

from abc import ABC
from types import MappingProxyType

import xmltodict
from marshmallow.fields import Constant

from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSchema, BaseSubSchema

XML_UNPARSE_ARGS = MappingProxyType(
    # used by tests
    {
        # Capitalize UTF-8 to be standard.
        "encoding": "UTF-8",
        "pretty": True,
        "short_empty_elements": True,
    }
)


class XmlRenderModule:
    """Marshmallow Render Module imitates json module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to XML string."""
        return xmltodict.unparse(
            obj,
            *args,
            **XML_UNPARSE_ARGS,
            **kwargs,
        )

    @staticmethod
    def loads(s: bytes | str, *args, **kwargs):
        """Load XML string into a dict."""
        cleaned_s: str | None = StringField().deserialize(s)  # type:ignore[reportAssignmentType]
        if cleaned_s:
            return xmltodict.parse(cleaned_s, *args, **kwargs)
        return None


class XmlSubSchema(BaseSubSchema, ABC):
    """XML Rendered Sub Schema."""

    class Meta(BaseSubSchema.Meta):
        """Schema Options."""

        render_module = XmlRenderModule


def create_xml_headers(
    ns: str, ns_uri: str, xsd_uri: str
) -> MappingProxyType[str, Constant]:
    """Create Namespace and Schema Location XML Attributes."""
    return MappingProxyType(
        {
            f"@xmlns:{ns}": Constant(ns_uri),
            "@xsi:schemaLocation": Constant(f"{ns_uri} {xsd_uri}"),
        }
    )


class XmlSubHeadSchema(XmlSubSchema, ABC):
    """XML Head Sub Schema customizations."""

    class Meta(XmlSubSchema.Meta):
        """Schema Options."""

        NS = ""
        NS_URI = ""
        XSD_URI = ""

        include = MappingProxyType(
            {
                "@xmlns:xsd": Constant("http://www.w3.org/2001/XMLSchema"),
                "@xmlns:xsi": Constant("http://www.w3.org/2001/XMLSchema-instance"),
            }
        )


class XmlSchema(BaseSchema, ABC):
    """Xml Rendered Schema."""

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = XmlRenderModule
