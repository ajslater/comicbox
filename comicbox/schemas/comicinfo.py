"""A class to encapsulate ComicRack's ComicInfo.xml data."""
# https://anansi-project.github.io/docs/comicinfo/schemas/v2.1

from types import MappingProxyType

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import ListField
from comicbox.fields.comicinfo import ComicInfoAgeRatingField
from comicbox.fields.enum_fields import PageTypeField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import IntegerField
from comicbox.fields.xml_fields import (
    XmlBooleanAttributeField,
    XmlComicInfoMangaField,
    XmlDecimalField,
    XmlIntegerField,
    XmlIntegerListField,
    XmlLanguageField,
    XmlOriginalFormatField,
    XmlStringField,
    XmlStringListField,
    XmlStringSetField,
    XmlYesNoField,
    create_sub_tag_field,
)
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubHeadSchema,
    XmlSubSchema,
    create_xml_headers,
)

ALTERNATE_SERIES_TAG = "AlternateSeries"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_COUNT_TAG = "AlternateCount"
GTIN_TAG = "GTIN"
IMAGE_ATTRIBUTE = "@Image"
BOOKMARK_ATTRIBUTE = "@Bookmark"
WEB_TAG = "Web"


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


class XmlPageInfoSchema(XmlSubSchema):
    """ComicPageInfo Structure for ComicInfo.xml."""

    class Meta(XmlSubSchema.Meta):
        """Illegal Field Names."""

        include = MappingProxyType(
            {
                BOOKMARK_ATTRIBUTE: StringField(),
                "@DoublePage": XmlBooleanAttributeField(),
                "@Key": StringField(),
                IMAGE_ATTRIBUTE: IntegerField(minimum=0),
                "@ImageWidth": IntegerField(minimum=0),
                "@ImageHeight": IntegerField(minimum=0),
                "@ImageSize": IntegerField(minimum=0),
                "@Type": PageTypeField(),
            }
        )


class ComicInfoSubSchema(XmlSubHeadSchema):
    """ComicInfo.xml Sub Schema."""

    # ComicInfo.xsd specifies this tag order
    TAG_ORDER: tuple[str, ...] = TAG_ORDER

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
    Manga = XmlComicInfoMangaField()
    Characters = XmlStringSetField(as_string=True)
    Teams = XmlStringSetField(as_string=True)
    Locations = XmlStringSetField(as_string=True)
    ScanInformation = XmlStringField()
    StoryArc = XmlStringListField(as_string=True, sort=False)
    StoryArcNumber = XmlIntegerListField(as_string=True)
    SeriesGroup = XmlStringSetField(as_string=True)
    AgeRating = ComicInfoAgeRatingField()
    Pages = create_sub_tag_field(
        "Page", ListField(Nested(XmlPageInfoSchema), sort_keys=(IMAGE_ATTRIBUTE,))
    )
    CommunityRating = XmlDecimalField()
    MainCharacterOrTeam = XmlStringSetField(as_string=True)
    Review = XmlStringField()
    GTIN = XmlStringSetField(as_string=True)

    class Meta(XmlSubHeadSchema.Meta):
        """Schema options."""

        NS = "comicinfo"
        NS_URI = "https://anansi-project.github.io/docs/comicinfo/schemas/v2.1"
        XSD_URI = "https://raw.githubusercontent.com/anansi-project/comicinfo/refs/heads/main/drafts/v2.1/ComicInfo.xsd"

        include = create_xml_headers(NS, NS_URI, XSD_URI)


class ComicInfoSchema(XmlSchema):
    """ComicInfo.xml Schema."""

    ROOT_TAG: str = "ComicInfo"
    ROOT_KEYPATH: str = ROOT_TAG
    TAG_ORDER: tuple[str, ...] = (ROOT_TAG,)
    HAS_PAGE_COUNT: bool = True
    HAS_PAGES: bool = True

    ComicInfo = Nested(ComicInfoSubSchema)
