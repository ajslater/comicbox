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
    XmlComicInfoMangaField,
    XmlDecimalField,
    XmlEnumField,
    XmlIntegerField,
    XmlIntegerListField,
    XmlLanguageField,
    XmlOriginalFormatField,
    XmlStringField,
    XmlStringListField,
    XmlStringSetField,
    XmlYesNoField,
)
from comicbox.schemas.age_rating_enum import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.comicinfo_enum import ComicInfoAgeRatingEnum
from comicbox.schemas.metroninfo import MetronAgeRatingEnum
from comicbox.schemas.xml_schemas import XmlSchema, XmlSubSchema, create_sub_tag_field

ALTERNATE_SERIES_TAG = "AlternateSeries"
ALTERNATE_NUMBER_TAG = "AlternateNumber"
ALTERNATE_COUNT_TAG = "AlternateCount"
GTIN_TAG = "GTIN"
IMAGE_ATTRIBUTE = "@Image"
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


COMICINFO_AGE_RATING_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        MarvelAgeRatingEnum.ALL_AGES: ComicInfoAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.PG: ComicInfoAgeRatingEnum.E_10_PLUS,
        MarvelAgeRatingEnum.PG_PLUS: ComicInfoAgeRatingEnum.E_10_PLUS,
        MarvelAgeRatingEnum.PARENTAL_ADVISORY: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.PSR: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MarvelAgeRatingEnum.PSR_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.A: ComicInfoAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.T_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.T: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MarvelAgeRatingEnum.EXPLICIT_CONTENT: ComicInfoAgeRatingEnum.X_18_PLUS,
        DCAgeRatingEnum.E: ComicInfoAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.EVERYONE: ComicInfoAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.T: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.TEEN: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.T_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.TEEN_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.M: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.MATURE: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.THIRTEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.FIFTEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.SEVENTEEN_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        GenericAgeRatingEnum.PG13: ComicInfoAgeRatingEnum.MA_15_PLUS,
        GenericAgeRatingEnum.R: ComicInfoAgeRatingEnum.MA_17_PLUS,
        GenericAgeRatingEnum.X: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.XXX: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.ADULT: ComicInfoAgeRatingEnum.A_18_PLUS,
        GenericAgeRatingEnum.PORN: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.PORNOGRAPHY: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.SEX: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.SEXUALLY_EXPLICIT: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.VIOLENT: ComicInfoAgeRatingEnum.A_18_PLUS,
        GenericAgeRatingEnum.VIOLENCE: ComicInfoAgeRatingEnum.A_18_PLUS,
        MetronAgeRatingEnum.EVERYONE: ComicInfoAgeRatingEnum.EVERYONE,
        MetronAgeRatingEnum.TEEN: ComicInfoAgeRatingEnum.TEEN,
        MetronAgeRatingEnum.TEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MetronAgeRatingEnum.MATURE: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MetronAgeRatingEnum.EXPLICIT: ComicInfoAgeRatingEnum.R_18_PLUS,
        MetronAgeRatingEnum.ADULT: ComicInfoAgeRatingEnum.X_18_PLUS,
    }
)


class ComicInfoAgeRatingField(XmlEnumField):
    """Age Rating Field."""

    ENUM = ComicInfoAgeRatingEnum
    ENUM_ALIAS_MAP = COMICINFO_AGE_RATING_MAP


class XmlPageInfoSchema(BaseSubSchema):
    """ComicPageInfo Structure for ComicInfo.xml."""

    class Meta(BaseSubSchema.Meta):
        """Illegal Field Names."""

        include = MappingProxyType(
            {
                "@Bookmark": StringField(),
                "@DoublePage": XmlBooleanAttributeField(),
                "@Key": StringField(),
                IMAGE_ATTRIBUTE: IntegerField(minimum=0),
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
    ROOT_KEY_PATH = ROOT_TAG
    TAG_ORDER = (ROOT_TAG,)
    HAS_PAGE_COUNT = True
    HAS_PAGES = True

    ComicInfo = Nested(ComicInfoSubSchema)
