"""Metron Price Schema."""

from decimal import Decimal
from types import MappingProxyType

from comicbox.fields.number_fields import DecimalField
from comicbox.fields.pycountry import CountryField
from comicbox.schemas.xml_schemas import XmlSubSchema


class BugfixComplexDecimalField(DecimalField):
    """Fix bug in xmltodict."""

    def _serialize(self, value, attr, obj, **kwargs):
        """Fix bug in xmltodict."""
        # https://github.com/martinblech/xmltodict/issues/366
        result = super()._serialize(value, attr, obj, **kwargs)
        return str(result)


class MetronPriceSchema(XmlSubSchema):
    """Metron Price Schema."""

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": BugfixComplexDecimalField(
                    required=True, places=2, minimum=Decimal(0)
                ),
                "@country": CountryField(),
            }
        )
