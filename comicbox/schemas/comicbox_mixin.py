"""Mixin for Comicbox Schemas."""

from decimal import Decimal

from marshmallow.fields import Nested
from marshmallow_union import Union

from comicbox.fields.collection_fields import (
    DictField,
    IdentifiersField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
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
CREDITS_KEY = "credits"
COUNTRY_KEY = "country"
DATE_KEY = "date"
DAY_KEY = "day"
DESIGNATION_KEY = "designation"
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
PERSON_KEY = "person"
PUBLISHER_KEY = "publisher"
PRICES_KEY = "prices"
PRICE_KEY = "price"
REPRINTS_KEY = "reprints"
REPRINT_ISSUE_KEY = "issue"
REPRINT_SERIES_KEY = "series"
ROLES_KEY = "roles"
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
UNIVERSES_KEY = "universes"
UPDATED_AT_KEY = "updated_at"
VOLUME_KEY = "volume"
VOLUME_COUNT_KEY = "volume_count"
VOLUME_ISSUE_COUNT_KEY = "issue_count"
VOLUME_NUMBER_KEY = "number"
WEB_KEY = "web"
YEAR_KEY = "year"

ORDERED_SET_KEYS = frozenset({"remainders"})
# haxxxxxxxxxxxxxxx
MAP_KEYS = frozenset(
    {
        CHARACTERS_KEY,
        CREDITS_KEY,
        GENRES_KEY,
        LOCATIONS_KEY,
        PRICES_KEY,
        STORIES_KEY,
        STORY_ARCS_KEY,
        TAGS_KEY,
        TEAMS_KEY,
        UNIVERSES_KEY,
    }
)


class IdentifiedSchema(BaseSubSchema):
    """Identified Schema."""

    identifiers = IdentifiersField()


class IdentifiedNameSchema(IdentifiedSchema):
    """Named Element with an identifier."""

    name = StringField()


class PersonSchema(BaseSubSchema):
    """Credit Person Schema."""

    identifiers = IdentifiersField()
    roles = DictField(values=Nested(IdentifiedSchema))


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

    identifiers = IdentifiersField()
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


class UniverseSchema(IdentifiedSchema):
    """Universe Schema."""

    designation = StringField()


class StoryArcSchema(BaseSubSchema):
    """Story Arc Schema."""

    identifiers = IdentifiersField()
    number = IntegerField()


class ComicboxSubSchemaMixin:
    """Mixin for Comicbox Sub Schemas."""

    age_rating = StringField()
    alternate_images = StringSetField()
    characters = DictField(values=Nested(IdentifiedSchema))
    community_rating = DecimalField(places=2)
    credits = DictField(values=Nested(PersonSchema))
    country = CountryField()
    collection_title = StringField()
    cover_image = StringField()
    critical_rating = DecimalField(places=2)
    date = DateField()
    day = IntegerField(minimum=1, maximum=31)
    ext = StringField()
    original_format = OriginalFormatField()
    genres = DictField(values=Nested(IdentifiedSchema))
    identifiers = IdentifiersField()
    identifier_primary_source = Nested(IdentifierPrimarySource)
    issue = StringField()
    issue_number = DecimalField(minimum=Decimal(0))
    issue_suffix = StringField()
    imprint = Nested(IdentifiedNameSchema)
    language = LanguageField()
    last_mark = IntegerField(minimum=0)
    locations = DictField(values=Nested(IdentifiedSchema))
    manga = MangaField()
    month = IntegerField(minimum=1, maximum=12)
    monochrome = BooleanField()
    notes = StringField()
    page_count = IntegerField(minimum=0)
    pages = Nested(PageInfoSchema, many=True)
    publisher = Nested(IdentifiedNameSchema)
    prices = DictField(
        keys=CountryField(allow_empty=True),
        values=DecimalField(places=2, minimum=Decimal(0)),
        allow_empty=True,
        sort=False,
    )
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
    # Turn off sorting in the field if i can?
    stories = DictField(values=Nested(IdentifiedSchema), sort=False)
    story_arcs = DictField(values=Nested(StoryArcSchema))
    summary = StringField()
    tagger = StringField()
    tags = DictField(values=Nested(IdentifiedSchema))
    teams = DictField(values=Nested(IdentifiedSchema))
    universes = DictField(values=Nested(UniverseSchema))
    updated_at = DateTimeField()
    volume = Union([Nested(VolumeSchema), StringField()])
    year = IntegerField()
