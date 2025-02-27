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
    XmlStringField,
)
from comicbox.identifiers import (
    ANILIST_NID,
    COMICVINE_NID,
    GCD_NID,
    KITSU_NID,
    LCG_NID,
    MANGADEX_NID,
    MANGAUPDATES_NID,
    METRON_NID,
    MYANIMELIST_NID,
    NID_ORIGIN_MAP,
)
from comicbox.schemas.base import BaseSchema, BaseSubSchema
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


def _metron_resource_list_field() -> ListField:
    """Get metron union resource and simple text field."""
    return xml_list_polyfield(MetronResourceSchema, StringField())


class MetronAgeRatingEnum(Enum):
    """Metron Age Rating Types."""

    UNKNOWN = "Unknown"
    EVERYONE = "Everyone"
    TEEN = "Teen"
    TEEN_PLUS = "Teen Plus"
    MATURE = "Mature"
    EXPLICIT = "Explicit"
    ADULT = "Adult"


class MetronAgeRatingField(XmlEnumField):
    """Metron Age Rating Field."""

    ENUM = MetronAgeRatingEnum


class MetronSourceEnum(Enum):
    """Metron Valid Sources."""

    ANILIST = NID_ORIGIN_MAP[ANILIST_NID]
    COMICVINE = NID_ORIGIN_MAP[COMICVINE_NID]
    GCD = NID_ORIGIN_MAP[GCD_NID]
    KITSU = NID_ORIGIN_MAP[KITSU_NID]
    LCG = NID_ORIGIN_MAP[LCG_NID]
    MANGADEX = NID_ORIGIN_MAP[MANGADEX_NID]
    MANGAUPDATES = NID_ORIGIN_MAP[MANGAUPDATES_NID]
    METRON = NID_ORIGIN_MAP[METRON_NID]
    MYANIMELIST = NID_ORIGIN_MAP[MYANIMELIST_NID]


class MetronSourceField(XmlEnumField):
    """Metron Source Field."""

    ENUM = MetronSourceEnum


class MetronFormatField(XmlEnumField):
    """Metron Series Format Field."""

    class MetronFormatEnum(Enum):
        """Metron Series Format Values."""

        ANNUAL = "Annual"
        DIGITAL_CHAPTER = "Digital Chapter"
        GRAPHIC_NOVEL = "Graphic Novel"
        HARDCOVER = "Hardcover"
        LIMITED_SERIES = "Limited Series"
        OMNIBUS = "Omnibus"
        ONE_SHOT = "One-Shot"
        SINGLE_ISSUE = "Single Issue"
        TRADE_PAPERBACK = "Trade Paperback"

    ENUM = MetronFormatEnum


class MetronRoleEnum(Enum):
    """Valid Metron Roles."""

    WRITER = "Writer"
    SCRIPT = "Script"
    STORY = "Story"
    PLOT = "Plot"
    INTERVIEWER = "Interviewer"
    ARTIST = "Artist"
    PENCILLER = "Penciller"
    BREAKDOWNS = "Breakdowns"
    ILLUSTRATOR = "Illustrator"
    LAYOUTS = "Layouts"
    INKER = "Inker"
    EMBELLISHER = "Embellisher"
    FINISHES = "Finishes"
    INK_ASSISTS = "Ink Assists"
    COLORIST = "Colorist"
    COLOR_SEPARATIONS = "Color Separations"
    COLOR_ASSISTS = "Color Assists"
    COLOR_FLATS = "Color Flats"
    DIGITAL_ART_TECHNICIAN = "Digital Art Technician"
    GRAY_TONE = "Gray Tone"
    LETTERER = "Letterer"
    COVER = "Cover"
    EDITOR = "Editor"
    CONSULTING_EDITOR = "Consulting Editor"
    ASSISTANT_EDITOR = "Assistant Editor"
    ASSOCIATE_EDITOR = "Associate Editor"
    GROUP_EDITOR = "Group Editor"
    SENIOR_EDITOR = "Senior Editor"
    MANAGING_EDITOR = "Managing Editor"
    COLLECTION_EDITOR = "Collection Editor"
    PRODUCTION = "Production"
    DESIGNER = "Designer"
    LOGO_DESIGN = "Logo Design"
    TRANSLATOR = "Translator"
    SUPERVISING_EDITOR = "Supervising Editor"
    EXECUTIVE_EDITOR = "Executive Editor"
    EDITOR_IN_CHIEF = "Editor In Chief"
    PRESIDENT = "President"
    PUBLISHER = "Publisher"
    CHIEF_CREATIVE_OFFICER = "Chief Creative Officer"
    EXECUTIVE_PRODUCER = "Executive Producer"
    OTHER = "Other"


class MetronRoleEnumField(XmlEnumField):
    """Metron Role Enum Field."""

    ENUM = MetronRoleEnum


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
        Nested(MetronNameSchema, many=True),
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
        "ID", ListField(Nested(MetronIDSchema), sort_key="@source")
    )
    Publisher = Nested(MetronPublisherSchema)
    Series = Nested(MetronSeriesSchema)
    MangaVolume = XmlStringField()
    CollectionTitle = XmlStringField()
    Number = XmlStringField()
    Stories = create_sub_tag_field("Story", _metron_resource_list_field())
    Summary = XmlStringField()
    Prices = create_sub_tag_field(
        "Price",
        xml_list_polyfield(
            MetronPriceSchema,
            BugfixComplexDecimalField(places=2, minimum=Decimal(0)),
            sort_key="@country",
        ),
    )
    CoverDate = XmlDateField()
    StoreDate = XmlDateField()
    PageCount = XmlIntegerField(minimum=0)
    Notes = XmlStringField()
    Genres = create_sub_tag_field("Genre", _metron_resource_list_field())
    Tags = create_sub_tag_field("Tag", _metron_resource_list_field())
    Arcs = create_sub_tag_field(
        "Arc", ListField(Nested(MetronArcSchema), sort_key="Name")
    )
    Characters = create_sub_tag_field("Character", _metron_resource_list_field())
    Teams = create_sub_tag_field("Team", _metron_resource_list_field())
    Universes = create_sub_tag_field(
        "Universe", ListField(Nested(MetronUniverseSchema), sort_key="Name")
    )
    Locations = create_sub_tag_field("Location", _metron_resource_list_field())
    Reprints = create_sub_tag_field("Reprint", _metron_resource_list_field())
    GTIN = Nested(MetronGTINSchema)
    AgeRating = MetronAgeRatingField()
    URLs = create_sub_tag_field(
        "URL", xml_list_polyfield(MetronURLSchema, StringField())
    )
    Credits = create_sub_tag_field(
        "Credit", ListField(Nested(MetronCreditSchema), sort_key="Creator.#text")
    )
    LastModified = XmlDateTimeField()

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
