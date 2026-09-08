"""Metron Publishing Schemas."""

from types import MappingProxyType
from typing import Any

from typing_extensions import override

from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.metroninfo import (
    MetronFormatField,
    MetronIDAttrField,
)
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.formats.base.fields.pycountry import LanguageField
from comicbox.formats.base.fields.xml_fields import (
    XmlStringField,
    create_sub_tag_field,
    xml_list_polyfield,
)
from comicbox.formats.base.schemas.xml_schemas import XmlSubSchema
from comicbox.formats.metron_info.schema.identifiers import MetronIdentifiedNameSchema
from comicbox.formats.metron_info.schema.resource import metron_resource_field


class MetronPublisherSchema(MetronIdentifiedNameSchema):
    """Metron Publisher Schema."""

    Imprint = metron_resource_field()


class MetronNameSchema(XmlSubSchema):
    """Metron Alternative Name Schema."""

    @classmethod
    @override
    def pre_load_validate(cls, data: Any) -> Any:
        """
        Accept a name written without attributes.

        ``lang`` defaults to en in the schema, so ``<AlternativeName>Foo</...>``
        is legal and parses as a bare string rather than a mapping.
        """
        if isinstance(data, str):
            return {"#text": data}
        return data

    class Meta(XmlSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(),
                # nameType declares `id` alongside `lang` in the XSD, and the
                # reprints transform already reads and writes it. Omitting it
                # here stripped the attribute before the transform ever saw it.
                "@id": MetronIDAttrField(),
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
        # lang defaults to en in the schema, so a name with no attributes is
        # a bare string, not a mapping.
        xml_list_polyfield(MetronNameSchema, XmlStringField()),
    )

    class Meta(MetronIdentifiedNameSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "@lang": LanguageField(),
            }
        )
