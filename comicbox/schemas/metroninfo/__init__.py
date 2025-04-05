"""A class to encapsulate Metron's MetronInfo.xml data."""

# https://metron-project.github.io/docs/metroninfo/schemas/v1.0
from decimal import Decimal
from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import ListField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.xml_fields import (
    XmlDateField,
    XmlDateTimeField,
    XmlEnumField,
    XmlIntegerField,
    XmlListField,
    XmlStringField,
)
from comicbox.schemas.enums.maps import METRON_AGE_RATING_MAP
from comicbox.schemas.enums.metroninfo import MetronAgeRatingEnum
from comicbox.schemas.metroninfo.credits import MetronCreditSchema
from comicbox.schemas.metroninfo.identifiers import (
    MetronGTINSchema,
    MetronIdentifiedNameSchema,
    MetronIDSchema,
    MetronURLSchema,
)
from comicbox.schemas.metroninfo.price import (
    BugfixComplexDecimalField,
    MetronPriceSchema,
)
from comicbox.schemas.metroninfo.publishing import (
    MetronPublisherSchema,
    MetronSeriesSchema,
)
from comicbox.schemas.metroninfo.resource import metron_resource_list_field
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubSchema,
    create_sub_tag_field,
    xml_list_polyfield,
)

COUNTRY_ATTR = "@country"
CREATOR_TAG = "Creator"
DESIGNATION_TAG = "Designation"
LANG_ATTR = "@lang"
LAST_MODIFIED_TAG = "LastModified"
NAME_TAG = "Name"
NUMBER_TAG = "Number"
PUBLISHER_TAG = "Publisher"
IMPRINT_TAG = "Imprint"
SERIES_TAG = "Series"
VOLUME_TAG = "Volume"
MANGA_VOLUME_TAG = "MangaVolume"
ALTERNATIVE_NAMES_TAGPATH = f"{SERIES_TAG}.AlternativeNames.AlternativeName"


class MetronAgeRatingField(XmlEnumField):
    """Metron Age Rating Field."""

    ENUM = MetronAgeRatingEnum
    ENUM_ALIAS_MAP = METRON_AGE_RATING_MAP


class MetronArcSchema(MetronIdentifiedNameSchema):
    """Metron Story Arc Schema."""

    Number = IntegerField(minimum=0)


class MetronUniverseSchema(MetronIdentifiedNameSchema):
    """Metron Universe Schema."""

    Designation = XmlStringField()


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
    Stories = create_sub_tag_field("Story", metron_resource_list_field(sort=False))
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
    Genres = create_sub_tag_field("Genre", metron_resource_list_field())
    Tags = create_sub_tag_field("Tag", metron_resource_list_field())
    Arcs = create_sub_tag_field(
        "Arc", ListField(Nested(MetronArcSchema), sort_keys=("Name",))
    )
    Characters = create_sub_tag_field("Character", metron_resource_list_field())
    Teams = create_sub_tag_field("Team", metron_resource_list_field())
    Universes = create_sub_tag_field(
        "Universe",
        ListField(Nested(MetronUniverseSchema), sort_keys=("Name", "Designation")),
    )
    Locations = create_sub_tag_field("Location", metron_resource_list_field())
    Reprints = create_sub_tag_field("Reprint", metron_resource_list_field())
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
    ROOT_KEY_PATH = ROOT_TAG
    HAS_PAGE_COUNT = True

    MetronInfo = Nested(MetronInfoSubSchema)
