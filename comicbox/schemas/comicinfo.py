"""A class to encapsulate ComicRack's ComicInfo.xml data."""
# https://anansi-project.github.io/docs/comicinfo/schemas/v2.1

from enum import Enum
from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.fields.xml_fields import (
    XmlCountryField,
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
                "@DoublePage": BooleanField(),
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

    AgeRating = ComicInfoAgeRatingField()
    AlternateCount = XmlIntegerField(minimum=0)
    AlternateNumber = XmlStringField()
    AlternateSeries = XmlStringField()
    BlackAndWhite = XmlYesNoField()
    Characters = XmlStringSetField(as_string=True)
    CommunityRating = XmlDecimalField()
    Country = XmlCountryField()
    Count = XmlIntegerField(minimum=0)
    Day = XmlIntegerField(minimum=0, maximum=31)
    Genre = XmlStringSetField(as_string=True)
    GTIN = XmlStringSetField(as_string=True)
    Format = XmlOriginalFormatField()
    Imprint = XmlStringField()
    LanguageISO = XmlLanguageField()
    Locations = XmlStringSetField(as_string=True)
    MainCharacterOrTeam = XmlStringSetField(as_string=True)
    Manga = XmlMangaField()
    Month = XmlIntegerField(minimum=0, maximum=12)
    Notes = XmlStringField()
    Number = XmlStringField()
    PageCount = XmlIntegerField(minimum=0)  # recaluculated by comicbox
    Pages = create_sub_tag_field("Page", Nested(XmlPageInfoSchema, many=True))
    Publisher = XmlStringField()
    Review = XmlStringField()
    ScanInformation = XmlStringField()
    Series = XmlStringField()
    SeriesGroup = XmlStringSetField(as_string=True)
    StoryArc = XmlStringListField(as_string=True, sort=False)
    StoryArcNumber = XmlIntegerListField(as_string=True, sort=False)
    Tags = XmlStringSetField(as_string=True)
    Teams = XmlStringSetField(as_string=True)
    Title = XmlStringField()
    Translator = XmlStringField()
    Summary = XmlStringField()
    Volume = XmlIntegerField()
    Web = XmlStringSetField(separators=" ", as_string=True)
    Year = XmlIntegerField()

    # Role Tags
    Colorist = XmlStringSetField(as_string=True)
    CoverArtist = XmlStringSetField(as_string=True)
    Editor = XmlStringSetField(as_string=True)
    Inker = XmlStringSetField(as_string=True)
    Letterer = XmlStringSetField(as_string=True)
    Penciller = XmlStringSetField(as_string=True)
    Writer = XmlStringSetField(as_string=True)

    class Meta(XmlSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1"
                ),
            }
        )


class ComicInfoSchema(XmlSchema):
    """ComicInfo.xml Schema."""

    CONFIG_KEYS = frozenset(
        {"cr", "ci", "cix", "comicinfo", "comicinfoxml", "comicrack"}
    )
    FILENAME = "ComicInfo.xml"  # Comictagger doesn't read without CapCase
    ROOT_TAGS = ("ComicInfo",)

    ComicInfo = Nested(ComicInfoSubSchema)
