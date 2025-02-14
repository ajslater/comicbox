"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.fields.xml_fields import (
    XmlAgeRatingField,
    XmlCountryField,
    XmlDecimalField,
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
from comicbox.schemas.xml_schemas import XmlSchema, XmlSubSchema
from comicbox.schemas.xml_sub_tags import create_sub_tag_field

GTIN_TAG = "GTIN"

COLORIST_TAG = "Colorist"
COVER_ARTIST_TAG = "CoverArtist"
CREATOR_TAG = "Creator"
EDITOR_TAG = "Editor"
INKER_TAG = "Inker"
LETTTER_TAG = "Letterer"
PENCILLER_TAG = "Penciller"
WRITER_TAG = "Writer"


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

    # https://anansi-project.github.io/docs/comicinfo/schemas/v2.1
    AgeRating = XmlAgeRatingField()
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
    Summary = XmlStringField()
    Volume = XmlIntegerField()
    Web = XmlStringSetField(separators=" ", as_string=True)
    Year = XmlIntegerField()

    # Contributors
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
