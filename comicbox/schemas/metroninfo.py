"""A class to encapsulate Metron's MetronInfo.xml data."""

# https://metron-project.github.io/docs/metroninfo/schemas/v1.0
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from marshmallow.fields import Constant, Field, Nested

from comicbox.fields.collection_fields import ListField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.xml_fields import (
    XmlBooleanAttributeField,
    XmlDateField,
    XmlDateTimeField,
    XmlEnumField,
    XmlIntegerField,
    XmlListField,
    XmlStringField,
)
from comicbox.schemas.age_rating_enum import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicinfo_enum import ComicInfoAgeRatingEnum
from comicbox.schemas.metroninfo_enum import (
    GenericFormatEnum,
    MetronAgeRatingEnum,
    MetronFormatEnum,
    MetronRoleEnum,
    MetronSourceEnum,
)
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubSchema,
    create_sub_tag_field,
    xml_list_polyfield,
    xml_polyfield,
)

LAST_MODIFIED_TAG = "LastModified"


class MetronIDAttrField(StringField):
    """Metron ID Field."""


class MetronResourceSchema(BaseSubSchema):
    """Metron Resource Schema."""

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": StringField(required=True), "@id": MetronIDAttrField()}
        )


def _metron_resource_field() -> Field:
    """Get metron union resource and simple text field."""
    return xml_polyfield(MetronResourceSchema, StringField())


def _metron_resource_list_field(**kwargs) -> ListField:
    """Get metron union resource and simple text field."""
    return xml_list_polyfield(MetronResourceSchema, StringField(), **kwargs)


METRON_AGE_RATING_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        MarvelAgeRatingEnum.ALL_AGES: MetronAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.PG: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.PG_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.PARENTAL_ADVISORY: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.PSR: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.PSR_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.A: MetronAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.T_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.T: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.EXPLICIT_CONTENT: MetronAgeRatingEnum.EXPLICIT,
        DCAgeRatingEnum.E: MetronAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.EVERYONE: MetronAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.T: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.TEEN: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.T_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.TEEN_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.M: MetronAgeRatingEnum.MATURE,
        DCAgeRatingEnum.MATURE: MetronAgeRatingEnum.MATURE,
        DCAgeRatingEnum.THIRTEEN_PLUS: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.FIFTEEN_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.SEVENTEEN_PLUS: MetronAgeRatingEnum.MATURE,
        GenericAgeRatingEnum.PG13: MetronAgeRatingEnum.TEEN,
        GenericAgeRatingEnum.R: MetronAgeRatingEnum.MATURE,
        GenericAgeRatingEnum.X: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.XXX: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.ADULT: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.PORN: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.PORNOGRAPHY: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.SEX: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.SEXUALLY_EXPLICIT: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.VIOLENT: MetronAgeRatingEnum.EXPLICIT,
        GenericAgeRatingEnum.VIOLENCE: MetronAgeRatingEnum.EXPLICIT,
        ComicInfoAgeRatingEnum.EVERYONE: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.EARLY_CHILDHOOD: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.E_10_PLUS: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.G: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.KIDS_TO_ADULTS: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.TEEN: MetronAgeRatingEnum.TEEN,
        ComicInfoAgeRatingEnum.PG: MetronAgeRatingEnum.TEEN,
        ComicInfoAgeRatingEnum.MA_15_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        ComicInfoAgeRatingEnum.M: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.MA_17_PLUS: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.R_18_PLUS: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.X_18_PLUS: MetronAgeRatingEnum.EXPLICIT,
        ComicInfoAgeRatingEnum.A_18_PLUS: MetronAgeRatingEnum.ADULT,
    }
)


class MetronAgeRatingField(XmlEnumField):
    """Metron Age Rating Field."""

    ENUM = MetronAgeRatingEnum
    ENUM_ALIAS_MAP = METRON_AGE_RATING_MAP


METRON_FORMAT_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        # GenericFormatEnum.ANTHOLOGY: MetronFormatEnum.,
        # GenericFormatEnum.ANNOTATION: MetronFormatEnum.,
        GenericFormatEnum.BOX_SET: MetronFormatEnum.OMNIBUS,
        GenericFormatEnum.DIGITAL: MetronFormatEnum.DIGITAL_CHAPTER,
        # GenericFormatEnum.DIRECTORS_CUT: MetronFormatEnum.,
        # GenericFormatEnum.DIRECTOR_S_CUT: MetronFormatEnum.,
        GenericFormatEnum.GIANT_SIZED: MetronFormatEnum.ANNUAL,
        GenericFormatEnum.GN: MetronFormatEnum.GRAPHIC_NOVEL,
        GenericFormatEnum.HARD_COVER: MetronFormatEnum.HARDCOVER,
        GenericFormatEnum.HC: MetronFormatEnum.HARDCOVER,
        GenericFormatEnum.HD_UPSCALED: MetronFormatEnum.DIGITAL_CHAPTER,
        GenericFormatEnum.KING_SIZED: MetronFormatEnum.ANNUAL,
        # GenericFormatEnum.MAGAZINE: MetronFormatEnum.,
        # GenericFormatEnum.MANGA: MetronFormatEnum.,
        GenericFormatEnum.ONE_DASH_SHOT: MetronFormatEnum.ONE_SHOT,
        # GenericFormatEnum.PDF_RIP: MetronFormatEnum.,
        # GenericFormatEnum.PREVIEW: MetronFormatEnum.,
        # GenericFormatEnum.PROLOGUE: MetronFormatEnum.,
        # GenericFormatEnum.SCANLATION: MetronFormatEnum.,
        # GenericFormatEnum.SCRIPT: MetronFormatEnum.,
        GenericFormatEnum.TBP: MetronFormatEnum.TRADE_PAPERBACK,
        # GenericFormatsEnum.WEB_COMIC: MetronFormatEnum.,
        # GenericFormatsEnum.WEB_RIP: MetronFormatEnum.,
    }
)


class MetronFormatField(XmlEnumField):
    """Metron Series Format Field."""

    ENUM = MetronFormatEnum
    ENUM_ALIAS_MAP = METRON_FORMAT_MAP


class MetronRoleEnumField(XmlEnumField):
    """Metron Role Enum Field."""

    ENUM = MetronRoleEnum


class MetronSourceField(XmlEnumField):
    """Metron Source Field."""

    ENUM = MetronSourceEnum


class MetronIDSchema(BaseSubSchema):
    """Metron ID Schema."""

    class Meta(BaseSubSchema.Meta):
        """Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(required=True),
                "@source": MetronSourceField(required=True),
                "@primary": XmlBooleanAttributeField(),
            }
        )


class MetronURLSchema(BaseSubSchema):
    """Metron URL Schema."""

    class Meta(BaseSubSchema.Meta):
        """Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(required=True),
                "@primary": XmlBooleanAttributeField(),
            }
        )


class MetronPublisherSchema(BaseSubSchema):
    """Metron Publisher Schema."""

    Name = XmlStringField()
    Imprint = _metron_resource_field()

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


class MetronNameSchema(BaseSubSchema):
    """Metron Alternative Name Schema."""

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": StringField(),
                "@lang": LanguageField(),
            }
        )


class MetronSeriesSchema(BaseSubSchema):
    """Metron Series Schema."""

    Name = XmlStringField()
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

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "@lang": LanguageField(),
                "@id": MetronIDAttrField(),
            }
        )


class BugfixComplexDecimalField(DecimalField):
    """Fix bug in xmltodict."""

    def _serialize(self, value, attr, obj, **kwargs):
        """Fix bug in xmltodict."""
        # https://github.com/martinblech/xmltodict/issues/366
        result = super()._serialize(value, attr, obj, **kwargs)
        return str(result)


class MetronPriceSchema(BaseSubSchema):
    """Metron Price Schema."""

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {
                "#text": BugfixComplexDecimalField(
                    required=True, places=2, minimum=Decimal(0)
                ),
                "@country": CountryField(),
            }
        )


class MetronGTINSchema(BaseSubSchema):
    """Metron GTIN Schema."""

    ISBN = XmlStringField()
    UPC = XmlStringField()


class MetronUniverseSchema(BaseSubSchema):
    """Metron Universe Schema."""

    Name = XmlStringField(required=True)
    Designation = XmlStringField()

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


class MetronArcSchema(BaseSubSchema):
    """Metron Story Arc Schema."""

    Name = XmlStringField()
    Number = IntegerField(minimum=0)

    class Meta(BaseSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType({"@id": MetronIDAttrField()})


class MetronRoleSchema(BaseSubSchema):
    """Metron Role Schema."""

    class Meta(BaseSubSchema.Meta):
        """XML Attributes."""

        include = MappingProxyType(
            {"#text": MetronRoleEnumField(), "@id": MetronIDAttrField()}
        )


class MetronCreditSchema(BaseSubSchema):
    """Metron Credit Schema."""

    Creator = _metron_resource_field()
    Roles = create_sub_tag_field(
        "Role", xml_list_polyfield(MetronRoleSchema, MetronRoleEnumField())
    )


class MetronInfoSubSchema(XmlSubSchema):
    """MetronInfo.xml Sub Schema."""

    IDS = create_sub_tag_field(
        "ID", ListField(Nested(MetronIDSchema), sort_keys=("@source",))
    )
    Publisher = Nested(MetronPublisherSchema)
    Series = Nested(MetronSeriesSchema)
    MangaVolume = XmlStringField()
    CollectionTitle = XmlStringField()
    Number = XmlStringField()
    Stories = create_sub_tag_field("Story", _metron_resource_list_field(sort=False))
    Summary = XmlStringField()
    Prices = create_sub_tag_field(
        "Price",
        xml_list_polyfield(
            MetronPriceSchema,
            BugfixComplexDecimalField(places=2, minimum=Decimal(0)),
            sort_keys=("@country",),
        ),
    )
    CoverDate = XmlDateField()
    StoreDate = XmlDateField()
    PageCount = XmlIntegerField(minimum=0)
    Notes = XmlStringField()
    Genres = create_sub_tag_field("Genre", _metron_resource_list_field())
    Tags = create_sub_tag_field("Tag", _metron_resource_list_field())
    Arcs = create_sub_tag_field(
        "Arc", ListField(Nested(MetronArcSchema), sort_keys=("Name",))
    )
    Characters = create_sub_tag_field("Character", _metron_resource_list_field())
    Teams = create_sub_tag_field("Team", _metron_resource_list_field())
    Universes = create_sub_tag_field(
        "Universe",
        ListField(Nested(MetronUniverseSchema), sort_keys=("Name", "Designation")),
    )
    Locations = create_sub_tag_field("Location", _metron_resource_list_field())
    Reprints = create_sub_tag_field("Reprint", _metron_resource_list_field())
    GTIN = Nested(MetronGTINSchema)
    AgeRating = MetronAgeRatingField()
    URLs = create_sub_tag_field(
        "URL", xml_list_polyfield(MetronURLSchema, StringField())
    )
    Credits = create_sub_tag_field(
        "Credit", XmlListField(Nested(MetronCreditSchema), sort_keys=("Creator",))
    )
    LastModified = XmlDateTimeField()

    class Meta(XmlSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType(
            {
                "@xmlns:metroninfo": Constant(
                    "https://metron-project.github.io/docs/metroninfo/schemas/v1.0"
                ),
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://metron-project.github.io/docs/metroninfo/schemas/v1.0 https://raw.githubusercontent.com/Metron-Project/metroninfo/refs/heads/master/schema/v1.0/MetronInfo.xsd"
                ),
            }
        )


class MetronInfoSchema(XmlSchema):
    """MetronInfo.xml Schema."""

    ROOT_TAG = "MetronInfo"
    WRAP_TAGS = (ROOT_TAG,)
    CONFIG_KEYS = frozenset({"metron", "metroninfo", "mi", "mix"})
    FILENAME = "MetronInfo.xml"

    MetronInfo = Nested(MetronInfoSubSchema)
