"""A class to encapsulate Metron's MetronInfo.xml data."""

# https://metron-project.github.io/docs/metroninfo/schemas/v1.0
from decimal import Decimal

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import ListField
from comicbox.fields.fields import StringField
from comicbox.fields.metroninfo import MetronAgeRatingField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.xml_fields import (
    XmlDateField,
    XmlDateTimeField,
    XmlIntegerField,
    XmlListField,
    XmlStringField,
    XmlTextDecimalField,
    create_sub_tag_field,
    xml_list_polyfield,
)
from comicbox.schemas.metroninfo.credits import MetronCreditSchema
from comicbox.schemas.metroninfo.identifiers import (
    MetronGTINSchema,
    MetronIdentifiedNameSchema,
    MetronIDSchema,
    MetronURLSchema,
)
from comicbox.schemas.metroninfo.price import (
    MetronPriceSchema,
)
from comicbox.schemas.metroninfo.publishing import (
    MetronPublisherSchema,
    MetronSeriesSchema,
)
from comicbox.schemas.metroninfo.resource import metron_resource_list_field
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubHeadSchema,
    create_xml_headers,
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


class MetronArcSchema(MetronIdentifiedNameSchema):
    """Metron Story Arc Schema."""

    Number = IntegerField(minimum=0)


class MetronUniverseSchema(MetronIdentifiedNameSchema):
    """Metron Universe Schema."""

    Designation = XmlStringField()


class MetronInfoSubSchema(XmlSubHeadSchema):
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
            XmlTextDecimalField(places=2, minimum=Decimal(0)),
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

    class Meta(XmlSubHeadSchema.Meta):
        """Schema Options."""

        NS = "metroninfo"
        NS_URI = "https://metron-project.github.io/docs/metroninfo/schemas/v1.0"
        XSD_URI = "https://raw.githubusercontent.com/Metron-Project/metroninfo/refs/heads/master/schema/v1.0/MetronInfo.xsd"

        include = create_xml_headers(NS, NS_URI, XSD_URI)


class MetronInfoSchema(XmlSchema):
    """MetronInfo.xml Schema."""

    ROOT_TAG: str = "MetronInfo"
    ROOT_KEYPATH: str = ROOT_TAG
    HAS_PAGE_COUNT: bool = True

    MetronInfo = Nested(MetronInfoSubSchema)
