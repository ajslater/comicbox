"""Metron Price Schema."""

from decimal import Decimal
from types import MappingProxyType

from comicbox.fields.pycountry import CountryField
from comicbox.fields.xml_fields import XmlTextDecimalField
from comicbox.schemas.xml_schemas import XmlSubSchema


class MetronPriceSchema(XmlSubSchema):
    """Metron Price Schema."""

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": XmlTextDecimalField(
                    required=True, places=2, minimum=Decimal(0)
                ),
                "@country": CountryField(),
            }
        )
