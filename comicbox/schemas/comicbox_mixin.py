"""Mixin for Comicbox Schemas."""

from decimal import Decimal

from marshmallow.fields import Nested
from marshmallow_union import Union

from comicbox.fields.collection_fields import (
    DictStringField,
    IdentifiersField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
    AgeRatingField,
    MangaField,
    OriginalFormatField,
    PageTypeField,
    ReadingDirectionField,
)
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.schemas.base import BaseSubSchema

ROOT_TAG = "comicbox"
AGE_RATING_KEY = "age_rating"
CHARACTERS_KEY = "characters"
CONTRIBUTORS_KEY = "contributors"
COUNTRY_KEY = "country"
DATE_KEY = "date"
DAY_KEY = "day"
GENRES_KEY = "genres"
IDENTIFIERS_KEY = "identifiers"
IDENTIFIER_PRIMARY_SOURCE_KEY = "identifier_primary_source"
IMPRINT_KEY = "imprint"
ISSUE_KEY = "issue"
ISSUE_NUMBER_KEY = "issue_number"
ISSUE_SUFFIX_KEY = "issue_suffix"
LANGUAGE_KEY = "language"
LOCATIONS_KEY = "locations"
MONTH_KEY = "month"
NAME_KEY = "name"
NUMBER_KEY = "number"
NID_KEY = "nid"
NOTES_KEY = "notes"
ORIGINAL_FORMAT_KEY = "original_format"
PAGES_KEY = "pages"
PAGE_COUNT_KEY = "page_count"
PAGE_INDEX_KEY = "index"
PAGE_TYPE_KEY = "page_type"
PUBLISHER_KEY = "publisher"
PRICES_KEY = "prices"
PRICE_KEY = "price"
REPRINTS_KEY = "reprints"
REPRINT_ISSUE_KEY = "issue"
REPRINT_SERIES_KEY = "series"
SCAN_INFO_KEY = "scan_info"
SERIES_KEY = "series"
SERIES_GROUPS_KEY = "series_groups"
SERIES_SORT_NAME_KEY = "sort_name"
SERIES_START_YEAR_KEY = "start_year"
STORIES_KEY = "stories"
STORY_ARCS_KEY = "story_arcs"
SUFFIX_KEY = "suffix"
SUMMARY_KEY = "summary"
TAGGER_KEY = "tagger"
TAGS_KEY = "tags"
TEAMS_KEY = "teams"
UPDATED_AT_KEY = "updated_at"
VOLUME_KEY = "volume"
VOLUME_COUNT_KEY = "volume_count"
VOLUME_ISSUE_COUNT_KEY = "issue_count"
VOLUME_NUMBER_KEY = "number"
WEB_KEY = "web"
YEAR_KEY = "year"

ORDERED_SET_KEYS = frozenset({"stories", "remainders"})


# CONTRIBUTOR ROLES
COLORIST_KEY = "colorist"
COVER_ARTIST_KEY = "cover_artist"
CREATOR_KEY = "creator"
EDITOR_KEY = "editor"
INKER_KEY = "inker"
LETTERER_KEY = "letterer"
PENCILLER_KEY = "penciller"
WRITER_KEY = "writer"


class IdentifiedNameSchema(BaseSubSchema):
    """Named Element with an identifier."""

    identifiers = IdentifiersField()
    name = StringField()


class ContributorsSchema(BaseSubSchema):
    """Contributors."""

    colorist = StringSetField()
    cover_artist = StringSetField()
    creator = StringSetField()
    editor = StringSetField()
    inker = StringSetField()
    letterer = StringSetField()
    penciller = StringSetField()
    writer = StringSetField()


class PageInfoSchema(BaseSubSchema):
    """Comicbox page info schema."""

    bookmark = StringField()
    double_page = BooleanField()
    key = StringField()
    index = IntegerField(minimum=0)
    width = IntegerField(minimum=0)
    height = IntegerField(minimum=0)
    size = IntegerField(minimum=0)
    page_type = PageTypeField()


# class IssueSchema(BaseSubSchema):
#    """Issue Schema."""
#
#    name = StringField() noqa: ERA001
#    number = DecimalField() noqa: ERA001
#    suffix = StringField() noqa: ERA001


class VolumeSchema(IdentifiedNameSchema):
    """Volume Schema."""

    issue_count = IntegerField(minimum=0)
    number = IntegerField(minimum=0)


class SeriesSchema(IdentifiedNameSchema):
    """Series Schema."""

    sort_name = StringField()
    start_year = IntegerField()
    volume_count = IntegerField(minimum=0)


class ReprintSchema(BaseSubSchema):
    """Schema for Reprints of this issue."""

    language = LanguageField()
    publisher = StringField()
    imprint = StringField()
    series = Nested(SeriesSchema)
    volume = Nested(VolumeSchema)
    issue = StringField()


class IdentifierPrimarySource(BaseSubSchema):
    """Identifiers Primary Source."""

    nid = StringField(required=True)
    url = StringField()


class PriceSchema(BaseSubSchema):
    """Price Schema."""

    country = CountryField()
    price = DecimalField(places=2, minimum=Decimal(0))


class ComicboxSubSchemaMixin:
    """Mixin for Comicbox Sub Schemas."""

    age_rating = AgeRatingField()
    alternate_images = StringSetField()
    characters = Nested(IdentifiedNameSchema, many=True)
    community_rating = DecimalField(places=2)
    contributors = Nested(ContributorsSchema)
    country = CountryField()
    collection_title = StringField()
    cover_image = StringField()
    critical_rating = DecimalField(places=2)
    date = DateField()
    day = IntegerField(minimum=1, maximum=31)
    ext = StringField()
    original_format = OriginalFormatField()
    genres = Nested(IdentifiedNameSchema, many=True)
    identifiers = IdentifiersField()
    identifier_primary_source = Nested(IdentifierPrimarySource)
    issue = StringField()
    issue_number = DecimalField(minimum=Decimal(0))
    issue_suffix = StringField()
    imprint = Nested(IdentifiedNameSchema)
    language = LanguageField()
    last_mark = IntegerField(minimum=0)
    locations = Nested(IdentifiedNameSchema, many=True)
    manga = MangaField()
    month = IntegerField(minimum=1, maximum=12)
    monochrome = BooleanField()
    notes = StringField()
    page_count = IntegerField(minimum=0)
    pages = Nested(PageInfoSchema, many=True)
    publisher = Nested(IdentifiedNameSchema)
    prices = Nested(PriceSchema, many=True)
    protagonist = StringField()
    reading_direction = ReadingDirectionField()
    remainders = StringListField()
    reprints = ListField(Nested(ReprintSchema))
    review = StringField()
    rights = StringField()
    scan_info = StringField()
    series = Union([Nested(SeriesSchema), StringField()])
    series_groups = StringSetField()
    store_date = DateField()
    stories = Nested(IdentifiedNameSchema, many=True)
    story_arcs = DictStringField(values=IntegerField())
    summary = StringField()
    tagger = StringField()
    tags = Nested(IdentifiedNameSchema, many=True)
    teams = Nested(IdentifiedNameSchema, many=True)
    updated_at = DateTimeField()
    volume = Union([Nested(VolumeSchema), StringField()])
    year = IntegerField()
