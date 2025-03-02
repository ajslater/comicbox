"""A class to encapsulate ComicRack's ComicInfo.xml data."""
# https://anansi-project.github.io/docs/comicinfo/schemas/v2.1

from enum import Enum
from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import ListField
from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.xml_fields import (
    XmlBooleanAttributeField,
    XmlDecimalField,
    XmlEnumField,
    XmlIntegerField,
    XmlIntegerListField,
    XmlLanguageField,
    XmlMangaField,
    XmlOriginalFormatField,
    XmlStringField,
    XmlStringListField,
    XmlStringSetField,
    XmlYesNoField,
)
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.xml_schemas import XmlSchema, XmlSubSchema, create_sub_tag_field

GTIN_TAG = "GTIN"


TAG_ORDER = (
    "@xmlns:xsd",
    "@xmlns:xsi",
    "@xsi:schemaLocation",
    "Title",
    "Series",
    "Number",
    "Count",
    "Volume",
    "AlternateSeries",
    "AlternateNumber",
    "AlternateCount",
    "Summary",
    "Notes",
    "Year",
    "Month",
    "Day",
    "Writer",
    "Penciller",
    "Inker",
    "Colorist",
    "Letterer",
    "CoverArtist",
    "Editor",
    "Translator",
    "Publisher",
    "Imprint",
    "Genre",
    "Tags",
    "Web",
    "PageCount",
    "LanguageISO",
    "Format",
    "BlackAndWhite",
    "Manga",
    "Characters",
    "Teams",
    "Locations",
    "ScanInformation",
    "StoryArc",
    "StoryArcNumber",
    "SeriesGroup",
    "AgeRating",
    "Pages",
    "CommunityRating",
    "MainCharacterOrTeam",
    "Review",
    "GTIN",
)


class ComicInfoRoleTagEnum(Enum):
    """ComicInfo Role tags."""

    COLORIST = "Colorist"
    COVER_ARTIST = "CoverArtist"
    EDITOR = "Editor"
    INKER = "Inker"
    LETTERER = "Letterer"
    PENCILLER = "Penciller"
    TRANSLATOR = "Translator"
    WRITER = "Writer"


class ComicInfoAgeRatingEnum(Enum):
    """ComicInfo Age Ratings."""

    UNKNOWN = "Unknown"
    A_18_PLUS = "Adults Only 18+"
    EARLY_CHILDHOOD = "Early Childhood"
    EVERYONE = "Everyone"
    E_10_PLUS = "Everyone 10+"
    G = "G"
    KIDS_TO_ADULTS = "Kids to Adults"
    M = "M"
    MA_15_PLUS = "MA15+"
    MA_17_PLUS = "Mature 17+"
    PG = "PG"
    R_18_PLUS = "R18+"
    PENDING = "Rating Pending"
    TEEN = "Teen"
    X_18_PLUS = "X18+"


class ComicInfoAgeRatingField(XmlEnumField):
    """Age Rating Field."""

    ENUM = ComicInfoAgeRatingEnum


class XmlPageInfoSchema(BaseSubSchema):
    """ComicPageInfo Structure for ComicInfo.xml."""

    class Meta(BaseSubSchema.Meta):
        """Illegal Field Names."""

        include = MappingProxyType(
            {
                "@Bookmark": StringField(),
                "@DoublePage": XmlBooleanAttributeField(),
                "@Key": StringField(),
                "@Image": IntegerField(minimum=0),
                "@ImageWidth": IntegerField(minimum=0),
                "@ImageHeight": IntegerField(minimum=0),
                "@ImageSize": IntegerField(minimum=0),
                "@Type": PageTypeField(),
            }
        )


class ComicInfoSubSchema(XmlSubSchema):
    """ComicInfo.xml Sub Schema."""

    # ComicInfo.xsd specifies this tag order
    TAG_ORDER = TAG_ORDER

    Title = XmlStringField()
    Series = XmlStringField()
    Number = XmlStringField()
    Count = XmlIntegerField(minimum=0)
    Volume = XmlIntegerField()
    AlternateSeries = XmlStringField()
    AlternateNumber = XmlStringField()
    AlternateCount = XmlIntegerField(minimum=0)
    Summary = XmlStringField()
    Notes = XmlStringField()
    Year = XmlIntegerField()
    Month = XmlIntegerField(minimum=0, maximum=12)
    Day = XmlIntegerField(minimum=0, maximum=31)
    # Start Role Tags
    Writer = XmlStringSetField(as_string=True)
    Penciller = XmlStringSetField(as_string=True)
    Inker = XmlStringSetField(as_string=True)
    Colorist = XmlStringSetField(as_string=True)
    Letterer = XmlStringSetField(as_string=True)
    CoverArtist = XmlStringSetField(as_string=True)
    Editor = XmlStringSetField(as_string=True)
    Translator = XmlStringField()
    # End Role Tags
    Publisher = XmlStringField()
    Imprint = XmlStringField()
    Genre = XmlStringSetField(as_string=True)
    Tags = XmlStringSetField(as_string=True)
    Web = XmlStringSetField(separators=" ", as_string=True)
    PageCount = XmlIntegerField(minimum=0)  # recaluculated by comicbox
    LanguageISO = XmlLanguageField()
    Format = XmlOriginalFormatField()
    BlackAndWhite = XmlYesNoField()
    Manga = XmlMangaField()
    Characters = XmlStringSetField(as_string=True)
    Teams = XmlStringSetField(as_string=True)
    Locations = XmlStringSetField(as_string=True)
    ScanInformation = XmlStringField()
    StoryArc = XmlStringListField(as_string=True, sort=False)
    StoryArcNumber = XmlIntegerListField(as_string=True)
    SeriesGroup = XmlStringSetField(as_string=True)
    AgeRating = ComicInfoAgeRatingField()
    Pages = create_sub_tag_field(
        "Page", ListField(Nested(XmlPageInfoSchema), sort_keys=("@Image",))
    )
    CommunityRating = XmlDecimalField()
    MainCharacterOrTeam = XmlStringSetField(as_string=True)
    Review = XmlStringField()
    GTIN = XmlStringSetField(as_string=True)

    class Meta(XmlSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@xmlns:comicinfo": Constant(
                    "https://anansi-project.github.io/docs/comicinfo/"
                ),
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://anansi-project.github.io/docs/comicinfo/ https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd"
                ),
            }
        )


class ComicInfoSchema(XmlSchema):
    """ComicInfo.xml Schema."""

    ROOT_TAG = "ComicInfo"
    WRAP_TAGS = (ROOT_TAG,)
    TAG_ORDER = (ROOT_TAG,)
    CONFIG_KEYS = frozenset(
        {"cr", "ci", "cix", "comicinfo", "comicinfoxml", "comicrack"}
    )
    FILENAME = "ComicInfo.xml"  # Comictagger doesn't read without CapCase

    ComicInfo = Nested(ComicInfoSubSchema)
