"""Metron Publishing Schemas."""

from types import MappingProxyType

from marshmallow.fields import Nested

from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.pycountry import LanguageField
from comicbox.fields.xml_fields import XmlEnumField, XmlListField, XmlStringField
from comicbox.schemas.enums.maps import METRON_FORMAT_MAP
from comicbox.schemas.enums.metroninfo import MetronFormatEnum
from comicbox.schemas.metroninfo.identifiers import MetronIdentifiedNameSchema
from comicbox.schemas.metroninfo.resource import metron_resource_field
from comicbox.schemas.xml_schemas import XmlSubSchema, create_sub_tag_field


class MetronPublisherSchema(MetronIdentifiedNameSchema):
    """Metron Publisher Schema."""

    Imprint = metron_resource_field()


class MetronFormatField(XmlEnumField):
    """Metron Series Format Field."""

    ENUM = MetronFormatEnum
    ENUM_ALIAS_MAP = METRON_FORMAT_MAP


class MetronNameSchema(XmlSubSchema):
    """Metron Alternative Name Schema."""

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(),
                "@lang": LanguageField(),
            }
        )


class MetronSeriesSchema(MetronIdentifiedNameSchema):
    """Metron Series Schema."""

    SortName = XmlStringField()
    Volume = IntegerField(minimum=0)
    IssueCount = IntegerField(minimum=0)
    VolumeCount = IntegerField(minimum=0)
    Format = MetronFormatField()
    StartYear = IntegerField(minimum=1000, maximum=9999)
    AlternativeNames = create_sub_tag_field(
        "AlternativeName",
        XmlListField(Nested(MetronNameSchema)),
    )

    class Meta(MetronIdentifiedNameSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "@lang": LanguageField(),
            }
        )
