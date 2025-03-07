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
CHARACTERS_KEY = "characters"
CONTRIBUTORS_KEY = "contributors"
DATE_KEY = "date"
DAY_KEY = "day"
GENRES_KEY = "genres"
IDENTIFIERS_KEY = "identifiers"
ISSUE_KEY = "issue"
ISSUE_COUNT_KEY = "issue_count"
ISSUE_NUMBER_KEY = "issue_number"
ISSUE_SUFFIX_KEY = "issue_suffix"
LANGUAGE_KEY = "language"
LOCATIONS_KEY = "locations"
MONTH_KEY = "month"
NOTES_KEY = "notes"
ORIGINAL_FORMAT_KEY = "original_format"
PAGES_KEY = "pages"
PAGE_COUNT_KEY = "page_count"
PUBLISHER_KEY = "publisher"
IMPRINT_KEY = "imprint"
PRICE_KEY = "price"
REPRINTS_KEY = "reprints"
SCAN_INFO_KEY = "scan_info"
SERIES_KEY = "series"
STORIES_KEY = "stories"
STORY_ARCS_KEY = "story_arcs"
TAGGER_KEY = "tagger"
UPDATED_AT_KEY = "updated_at"
TAGS_KEY = "tags"
TEAMS_KEY = "teams"
VOLUME_KEY = "volume"
WEB_KEY = "web"
YEAR_KEY = "year"

REPRINT_SERIES_KEY = "series"
REPRINT_ISSUE_KEY = "issue"

ORDERED_SET_KEYS = frozenset({"remainders"})

PAGE_TYPE_KEY = "page_type"

INDEX_KEY = "index"

# CONTRIBUTOR ROLES
COLORIST_KEY = "colorist"
COVER_ARTIST_KEY = "cover_artist"
CREATOR_KEY = "creator"
EDITOR_KEY = "editor"
INKER_KEY = "inker"
LETTERER_KEY = "letterer"
PENCILLER_KEY = "penciller"
WRITER_KEY = "writer"

SERIES_NAME_KEY = "name"
VOLUME_NUMBER_KEY = "name"
VOLUME_COUNT_KEY = "volume_count"


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


class GroupSubSchema(BaseSubSchema):
    """Group Schema."""

    name = StringField()
    aliases = StringSetField()
    identifiers = IdentifiersField()


class VolumeSchema(GroupSubSchema):
    """Volume Schema."""

    name = IntegerField()
    issue_count = IntegerField(minimum=0)


class SeriesSchema(GroupSubSchema):
    """Series Schema."""

    volume_count = IntegerField(minimum=0)


# class ImprintSchema(GroupSubSchema):
#    """Imprint Schema."""


# class PublisherSchema(GroupSubSchema):
#    """Publisher Schema."""


class ReprintSchema(BaseSubSchema):
    """Schema for Reprints of this issue."""

    publisher = StringField()
    imprint = StringField()
    series = Nested(SeriesSchema)
    volume = Nested(VolumeSchema)
    issue = StringField()


class ComicboxSubSchemaMixin:
    """Mixin for Comicbox Sub Schemas."""

    age_rating = AgeRatingField()
    alternate_images = StringSetField()
    characters = StringSetField()
    community_rating = DecimalField(places=2)
    contributors = Nested(ContributorsSchema)
    country = CountryField()
    cover_image = StringField()
    critical_rating = DecimalField(places=2)
    date = DateField()
    day = IntegerField(minimum=1, maximum=31)
    ext = StringField()
    original_format = OriginalFormatField()
    genres = StringSetField()
    identifiers = IdentifiersField()
    issue = StringField()
    issue_number = DecimalField(minimum=Decimal(0))
    issue_suffix = StringField()
    imprint = StringField()
    language = LanguageField()
    last_mark = IntegerField(minimum=0)
    locations = StringSetField()
    manga = MangaField()
    month = IntegerField(minimum=1, maximum=12)
    monochrome = BooleanField()
    notes = StringField()
    page_count = IntegerField(minimum=0)
    pages = Nested(PageInfoSchema, many=True)
    publisher = StringField()
    price = DecimalField(places=2, minimum=Decimal(0))
    protagonist = StringField()
    reading_direction = ReadingDirectionField()
    remainders = StringListField()
    reprints = ListField(Nested(ReprintSchema))
    review = StringField()
    rights = StringField()
    scan_info = StringField()
    series = Union([Nested(SeriesSchema), StringField()])
    series_groups = StringSetField()
    stories = StringSetField()
    story_arcs = DictStringField(values=IntegerField(allow_none=True))
    summary = StringField()
    tagger = StringField()
    tags = StringSetField()
    teams = StringSetField()
    title = StringField()
    title_aliases = StringSetField()
    updated_at = DateTimeField()
    volume = Union([Nested(VolumeSchema), StringField()])
    year = IntegerField()
