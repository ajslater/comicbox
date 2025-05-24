"""Mixin for Comicbox Schemas."""

from decimal import Decimal

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import (
    DictField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.comicbox import (
    NAME_KEY as _FIELD_NAME_KEY,
)
from comicbox.fields.comicbox import (
    PagesField,
    RoleField,
    SimpleNamedDictField,
    SimpleNamedNestedField,
)
from comicbox.fields.enum_fields import (
    AgeRatingField,
    ComicInfoMangaField,
    OriginalFormatField,
    ReadingDirectionField,
)
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.comicbox.identifiers import (
    IdentifiedSchema,
    IdentifierPrimarySource,
)
from comicbox.schemas.comicbox.publishing import (
    IssueSchema,
    ReprintSchema,
    SeriesSchema,
    VolumeSchema,
)

NAME_KEY = _FIELD_NAME_KEY
AGE_RATING_KEY = "age_rating"
APP_ID_KEY = "appID"
BOOKMARK_KEY = "bookmark"
CHARACTERS_KEY = "characters"
CREDITS_KEY = "credits"
CREDIT_PRIMARIES_KEY = "credit_primaries"
COLLECTION_TITLE_KEY = "collection_title"
COMMUNITY_RATING_KEY = "community_rating"
CRITICAL_RATING_KEY = "critical_rating"
COUNTRY_KEY = "country"
COVER_IMAGE_KEY = "cover_image"
COVER_DATE_KEY = "cover_date"
DATE_KEY = "date"
DAY_KEY = "day"
DESIGNATION_KEY = "designation"
EXT_KEY = "ext"
GENRES_KEY = "genres"
IDENTIFIERS_KEY = "identifiers"
IDENTIFIER_PRIMARY_SOURCE_KEY = "identifier_primary_source"
IMPRINT_KEY = "imprint"
ISSUE_KEY = "issue"
ISSUE_SUFFIX_KEY = "suffix"
LANGUAGE_KEY = "language"
LOCATIONS_KEY = "locations"
MANGA_KEY = "manga"
MONTH_KEY = "month"
MONOCHROME_KEY = "monochrome"
NUMBER_KEY = "number"
NUMBER_TO_KEY = "number_to"
ID_SOURCE_KEY = "id_source"
NOTES_KEY = "notes"
ORIGINAL_FORMAT_KEY = "original_format"
PAGES_KEY = "pages"
PAGE_BOOKMARK_KEY = "bookmark"
PAGE_COUNT_KEY = "page_count"
PAGE_INDEX_KEY = "index"  # only used in transform
PAGE_TYPE_KEY = "page_type"
PAGE_SIZE_KEY = "size"
PAGE_KEYS = frozenset(
    {
        PAGE_TYPE_KEY,
        PAGE_BOOKMARK_KEY,
        "height",
        "width",
        "double_page",
        "key",
        PAGE_SIZE_KEY,
    }
)
PERSON_KEY = "person"
PUBLISHER_KEY = "publisher"
PRICES_KEY = "prices"
PRICE_KEY = "price"
PROTAGONIST_KEY = "protagonist"
READING_DIRECTION_KEY = "reading_direction"
REMAINDERS_KEY = "remainders"
REPRINTS_KEY = "reprints"
REPRINT_ISSUE_KEY = "issue"
REPRINT_SERIES_KEY = "series"
REVIEW_KEY = "review"
RIGHTS_KEY = "rights"
ROLES_KEY = "roles"
SCAN_INFO_KEY = "scan_info"
SERIES_KEY = "series"
SERIES_GROUPS_KEY = "series_groups"
SERIES_SORT_NAME_KEY = "sort_name"
SERIES_START_YEAR_KEY = "start_year"
STORE_DATE_KEY = "store_date"
STORIES_KEY = "stories"
TITLE_KEY = "title"
ARCS_KEY = "arcs"
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
VOLUME_NUMBER_TO_KEY = "number_to"
WEB_KEY = "web"
YEAR_KEY = "year"


class ArcSchema(IdentifiedSchema):
    """Story Arc Schema."""

    number = IntegerField(minimum=0)  # CIX, Metron


class PersonSchema(IdentifiedSchema):
    """Credit Person Schema."""

    roles = SimpleNamedDictField(  # Comet, CIX, CBI, Metron
        keys=RoleField, allow_empty_values=True
    )


class UniverseSchema(IdentifiedSchema):
    """Universe Schema."""

    designation = StringField()  # Metron ONLY


class DateSchema(BaseSubSchema):
    """Date Schema."""

    cover_date = DateField()  # Comet, PDF, Metron
    store_date = DateField()  # Metron ONLY
    year = IntegerField()  # CIX, CBI, CT, Filename, Metron
    month = IntegerField(minimum=1, maximum=12)  # CBI, CIX, CT
    day = IntegerField(minimum=1, maximum=31)  # CBI, CIX


class ComicboxSubSchemaMixin(IdentifiedSchema):
    """Mixin for Comicbox Sub Schemas."""

    age_rating = AgeRatingField()  # CIX, Metron
    alternate_images = StringSetField()  # CT ONLY
    arcs = SimpleNamedDictField(values=Nested(ArcSchema))  # CIX, CT, Metron
    bookmark = IntegerField(minimum=0)  # Comet, CIX(pages), CT
    characters = SimpleNamedDictField()  # Comet, CIX, CT, Metron
    country = CountryField()  # CBI, CIX, CT, Metron
    credits = SimpleNamedDictField(  # Comet, CIX, CBI, Metron
        values=Nested(PersonSchema)
    )
    credit_primaries = DictField(values=RoleField)  # CBI ONLY
    collection_title = StringField()  # Metron ONLY
    cover_image = StringField()  # Comet ONLY, CT
    critical_rating = DecimalField(places=2)  # CBI, CIX
    date = Nested(DateSchema)
    ext = StringField()  # Filename ONLY
    original_format = OriginalFormatField()  # Comet, CT, Filename, CIX, Metron
    genres = SimpleNamedDictField()  # Comet, CBI, CIX, CT, Metron, PDF
    # identifiers from parent # Comet, CBI, CIX, CT, Metron,
    identifier_primary_source = Nested(IdentifierPrimarySource)  # Metron
    imprint = SimpleNamedNestedField()  # CIX, CT, Metron
    issue = Nested(IssueSchema)  # ALL
    language = LanguageField()  # Comet, CBI, CIX, CT, Metron
    locations = SimpleNamedDictField()  # CIX, CT, Metron
    manga = ComicInfoMangaField()  # CIX ONLY
    monochrome = BooleanField()  # CIX ONLY, CT
    notes = StringField()  # CT, Metron, CIX
    page_count = IntegerField(minimum=0)  # CIX, Comet, Metron, CBI
    pages = PagesField()  # CIX ONLY, CT
    publisher = SimpleNamedNestedField()  # Comet, CIX, CT, Metron
    prices = DictField(  # Comet, CT, Metron
        keys=CountryField(),
        values=DecimalField(places=2, minimum=Decimal(0)),
        allow_empty_keys=True,
        sort=False,
    )
    protagonist = StringField()  # CIX ONLY
    reading_direction = ReadingDirectionField()  # Comet ONLY
    remainders = StringListField()  # Filename ONLY
    reprints = ListField(  # Comet, CIX, CT, Metron
        Nested(ReprintSchema),
        sort_keys=(
            "language",
            "series.sort_name",
            "series.name",
            "volume.number",
            "volume.number_to",
            "issue",
        ),
    )
    review = StringField()  # CIX ONLY
    rights = StringField()  # Comet ONLY
    scan_info = StringField()  # CIX, Filename, PDF
    series = SimpleNamedNestedField(
        schema=SeriesSchema
    )  # Comet, CBI, CIX, Filename, Metron
    title = StringField()  # CB only synthesized from stories
    series_groups = StringSetField()  # CIX ONLY, CT
    stories = SimpleNamedDictField(sort=False)  # CBI, CT, Metron, PDF
    summary = StringField()  # Comet, CIX, CT, CBI, Metron
    tagger = StringField()  # CBI, PDF
    tags = SimpleNamedDictField()  # CBI, CT, Metron
    teams = SimpleNamedDictField()  # CIX, Metron, CT
    universes = SimpleNamedDictField(values=Nested(UniverseSchema))  # Metron ONLY
    updated_at = DateTimeField()  # CBI, Metron, PDF
    volume = SimpleNamedNestedField(  # Comet, CBI, CIX, Filename, Metron
        schema=VolumeSchema,
        field=IntegerField(minimum=0),
        name_key=NUMBER_KEY,
        primitive_type=int,
    )


class ComicboxSchemaMixin:
    """Mixin for comicbox schemas."""

    ROOT_TAG = "comicbox"
    ROOT_KEYPATH = ROOT_TAG
    HAS_PAGE_COUNT = True
