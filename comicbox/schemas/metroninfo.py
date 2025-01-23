"""A class to encapsulate Metron's MetronInfo.xml data."""

# https://metron-project.github.io/docs/metroninfo/schemas/v1.0
from types import MappingProxyType

from marshmallow.fields import Constant, Field, Nested
from marshmallow.schema import Schema
from marshmallow_union import Union

from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.xml_fields import (
    XmlAgeRatingField,
    XmlBooleanField,
    XmlDateField,
    XmlIntegerField,
    XmlStringField,
    XmlStringSetField,
)
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.xml_schemas import XmlSchema, XmlSubSchema
from comicbox.schemas.xml_sub_tags import (
    create_pages_field,
    create_sub_tag_field,
)


class MetronSourceSchema(BaseSubSchema):
    """Metron Metadata Source Schema."""

    class Meta(BaseSubSchema.Meta):
        """Attributes."""

        include = MappingProxyType(
            {"#text": IntegerField(minimum=0, required=True), "@source": StringField()}
        )


class MetronResourceSchema(BaseSubSchema):
    """Metron Resource Schema."""

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": StringField(required=True), "@id": IntegerField(minimum=0)}
        )


class MetronSeriesSchema(BaseSubSchema):
    """Metron Series Schema."""

    Name = StringField()
    SortName = StringField()
    Volume = IntegerField()
    Format = StringField()

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "@lang": LanguageField(),
                "@id": IntegerField(minimum=0),
            }
        )


class MetronPriceSchema(BaseSubSchema):
    """Metron Price Schema."""

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": DecimalField(required=True), "@country": CountryField()}
        )


class MetronGTINSchema(BaseSubSchema):
    """Metron GTIN Schema."""

    ISBN = StringField()
    UPC = StringField()


class MetronArcSchema(BaseSubSchema):
    """Metron Story Arc Schema."""

    Name = StringField()
    Number = IntegerField(minimum=0)

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": IntegerField(minimum=0)})


def _create_text_schema(field: Field):
    """Create a text schema with a designated field type."""
    schema_name = field.__class__.__name__ + "TextSchema"
    schema_meta_class = type(
        "Meta", (BaseSubSchema.Meta,), {"include": {"#text": field}}
    )
    return type(schema_name, (BaseSubSchema,), {"Meta": schema_meta_class})


def _get_xml_poly_text_field(
    field: Field | None = None,
    many: bool = False,  # noqa: FBT002
    collection_field: Field | None = None,
    schema_class: type[Schema] | None = None,
):
    """Get a union field of xml list variations."""
    fields = []
    if not schema_class and field:
        schema_class = _create_text_schema(field)
    if schema_class:
        fields.append(Nested(schema_class, many=many))
    if collection_field:
        fields.append(collection_field)
    if field:
        fields.append(field)
    return Union(fields)


def _get_metron_polyfield():
    """Get a metron union field of xml list variations."""
    return _get_xml_poly_text_field(
        many=True,
        collection_field=XmlStringSetField(),
        schema_class=MetronResourceSchema,
    )


def _get_metron_resource_field(
    schema_class: type[BaseSubSchema] = MetronResourceSchema,
    field_class: type[Field] = StringField,
):
    """Get metron union resource and simple text field."""
    return _get_xml_poly_text_field(field=field_class(), schema_class=schema_class)


class MetronCreditSchema(BaseSubSchema):
    """Metron Credit Schema."""

    Creator = _get_metron_resource_field()
    Roles = create_sub_tag_field("Role", _get_metron_polyfield())


class MetronInfoSubSchema(XmlSubSchema):
    """MetronInfo.xml Sub Schema."""

    ID = _get_metron_resource_field(
        schema_class=MetronSourceSchema, field_class=IntegerField
    )
    Publisher = _get_metron_resource_field()
    Series = Nested(MetronSeriesSchema)
    CollectionTitle = XmlStringField()
    Number = XmlStringField()
    Stories = create_sub_tag_field("Story", _get_metron_polyfield())
    Summary = XmlStringField()
    Prices = create_sub_tag_field(
        "Price", _get_metron_resource_field(MetronPriceSchema, DecimalField)
    )
    CoverDate = XmlDateField()
    StoreDate = XmlDateField()
    PageCount = XmlIntegerField(minimum=0)
    Notes = XmlStringField()
    Genres = create_sub_tag_field("Genre", _get_metron_polyfield())
    Tags = create_sub_tag_field("Tag", _get_metron_polyfield())
    Arcs = create_sub_tag_field("Arc", Nested(MetronArcSchema, many=True))
    Characters = create_sub_tag_field("Character", _get_metron_polyfield())
    Teams = create_sub_tag_field("Team", _get_metron_polyfield())
    Locations = create_sub_tag_field("Location", _get_metron_polyfield())
    Reprints = create_sub_tag_field("Reprint", _get_metron_polyfield())
    GTIN = Nested(MetronGTINSchema)
    BlackAndWhite = XmlBooleanField()
    AgeRating = XmlAgeRatingField()
    URL = XmlStringField()
    Credits = create_sub_tag_field("Credit", Nested(MetronCreditSchema, many=True))
    Pages = create_pages_field()

    class Meta(XmlSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType(
            {
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://metron-project.github.io/docs/metroninfo/schemas/v1.0"
                )
            }
        )


class MetronInfoSchema(XmlSchema):
    """MetronInfo.xml Schema."""

    CONFIG_KEYS = frozenset({"metron", "metroninfo", "mi"})
    FILENAME = "MetronInfo.xml"
    ROOT_TAGS = ("MetronInfo",)

    MetronInfo = Nested(MetronInfoSubSchema)
