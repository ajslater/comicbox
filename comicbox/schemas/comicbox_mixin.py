"""Mixin for Comicbox Schemas."""

from decimal import Decimal
from inspect import isclass
from types import MappingProxyType

from marshmallow import Schema
from marshmallow.fields import Field, Nested
from marshmallow_union import Union

from comicbox.fields.collection_fields import (
    DictField,
    IdentifiersField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
    AgeRatingField,
    ComicInfoMangaField,
    OriginalFormatField,
    PageTypeField,
    PrettifiedStringField,
    ReadingDirectionField,
)
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicinfo_enum import ComicInfoRoleTagEnum
from comicbox.schemas.metroninfo_enum import MetronRoleEnum
from comicbox.schemas.role_enum import GenericRoleEnum

AGE_RATING_KEY = "age_rating"
APP_ID_KEY = "appID"
CHARACTERS_KEY = "characters"
CREDITS_KEY = "credits"
CREDIT_PRIMARIES_KEY = "credit_primaries"
COLLECTION_TITLE_KEY = "collection_title"
COMMUNITY_RATING_KEY = "community_rating"
CRITICAL_RATING_KEY = "critical_rating"
COUNTRY_KEY = "country"
COVER_IMAGE_KEY = "cover_image"
DATE_KEY = "date"
DAY_KEY = "day"
DESIGNATION_KEY = "designation"
EXT_KEY = "ext"
GENRES_KEY = "genres"
IDENTIFIERS_KEY = "identifiers"
IDENTIFIER_PRIMARY_SOURCE_KEY = "identifier_primary_source"
IMPRINT_KEY = "imprint"
ISSUE_KEY = "issue"
ISSUE_NUMBER_KEY = "issue_number"
ISSUE_SUFFIX_KEY = "issue_suffix"
LAST_MARK_KEY = "last_mark"
LANGUAGE_KEY = "language"
LOCATIONS_KEY = "locations"
MONTH_KEY = "month"
MONOCHROME_KEY = "monochrome"
NAME_KEY = "name"
NUMBER_KEY = "number"
NUMBER_TO_KEY = "number_to"
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
WEB_KEY = "web"
YEAR_KEY = "year"


class IdentifiedSchema(BaseSubSchema):
    """Identified Schema."""

    identifiers = IdentifiersField()


class IdentifiedNameSchema(IdentifiedSchema):
    """Named Element with an identifier."""

    name = StringField()


class SimpleNamedDictField(Union):
    """A dict that also accepts a simple string set and builds a dict from that."""

    def __init__(
        self,
        *args,
        keys: Field | type[Field] = StringField,
        values: Field | type[Field] | None = None,
        **kwargs,
    ):
        """Create the union."""
        if values is None:
            values = Nested(IdentifiedSchema)
        fields = [DictField(keys=keys, values=values), StringSetField()]
        super().__init__(fields, *args, **kwargs)

    def _deserialize(self, value, attr, *args, **kwargs):
        result = super()._deserialize(value, attr, *args, **kwargs)
        if isinstance(result, set | frozenset):
            dict_value = {}
            for key in result:
                dict_value[key] = {}
                result = super()._deserialize(dict_value, attr, *args, **kwargs)
        return result


class SimpleNamedNestedField(Union):
    """Return a union of a nested schema and an alternate field."""

    def __init__(
        self,
        *args,
        schema: type[Schema] = IdentifiedNameSchema,
        field: Field | type[Field] = StringField,
        name_key: str = NAME_KEY,
        primitive_type: type = str,
        **kwargs,
    ):
        """Create the union."""
        self._name_key = name_key
        self._primitive_type = primitive_type
        if isclass(field):
            field = field()
        fields = [Nested(schema), field]
        super().__init__(fields, *args, **kwargs)

    def _deserialize(self, value, attr, *args, **kwargs):
        result = super()._deserialize(value, attr, *args, **kwargs)
        if isinstance(result, self._primitive_type):
            complex_value = {self._name_key: result}
            result = super()._deserialize(complex_value, attr, *args, **kwargs)
        return result


COMICBOX_ROLE_ALIAS_MAP = MappingProxyType(
    {
        **{enum: enum for enum in CoMetRoleTagEnum},
        **{enum: enum for enum in ComicBookInfoRoleEnum},
        **{enum: enum for enum in ComicInfoRoleTagEnum},
        **{enum: enum for enum in MetronRoleEnum},
        **{enum: enum for enum in GenericRoleEnum},
    }
)


class RoleField(PrettifiedStringField):
    """Prettified Role Field."""

    ENUM_ALIAS_MAP = COMICBOX_ROLE_ALIAS_MAP


class PersonSchema(BaseSubSchema):
    """Credit Person Schema."""

    identifiers = IdentifiersField()
    roles = SimpleNamedDictField(keys=RoleField)


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


class VolumeSchema(BaseSubSchema):
    """Volume Schema."""

    # No identifiers in metron

    issue_count = IntegerField(minimum=0)
    number = IntegerField(minimum=0)
    number_to = IntegerField(minimum=0)


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


class ArcSchema(BaseSubSchema):
    """Story Arc Schema."""

    identifiers = IdentifiersField()
    number = IntegerField()


class ComicboxSubSchemaMixin:
    """Mixin for Comicbox Sub Schemas."""

    age_rating = AgeRatingField()
    alternate_images = StringSetField()
    arcs = SimpleNamedDictField(values=Nested(ArcSchema))
    characters = SimpleNamedDictField()
    community_rating = DecimalField(places=2)
    credits = SimpleNamedDictField(values=Nested(PersonSchema))
    credit_primaries = DictField(values=DictField)
    country = CountryField()
    collection_title = StringField()
    cover_image = StringField()
    critical_rating = DecimalField(places=2)
    date = DateField()
    day = IntegerField(minimum=1, maximum=31)
    ext = StringField()
    original_format = OriginalFormatField()
    genres = SimpleNamedDictField()
    identifiers = IdentifiersField()
    identifier_primary_source = Nested(IdentifierPrimarySource)
    issue = StringField()
    issue_number = DecimalField(minimum=Decimal(0))
    issue_suffix = StringField()
    imprint = SimpleNamedNestedField()
    language = LanguageField()
    last_mark = IntegerField(minimum=0)
    locations = SimpleNamedDictField()
    manga = ComicInfoMangaField()
    month = IntegerField(minimum=1, maximum=12)
    monochrome = BooleanField()
    notes = StringField()
    page_count = IntegerField(minimum=0)
    pages = Nested(PageInfoSchema, many=True)
    publisher = SimpleNamedNestedField()
    prices = DictField(
        keys=CountryField(allow_empty=True),
        values=DecimalField(places=2, minimum=Decimal(0)),
        allow_empty=True,
        sort=False,
    )
    protagonist = StringField()
    reading_direction = ReadingDirectionField()
    remainders = StringListField()
    reprints = ListField(
        Nested(ReprintSchema),
        sort_keys=(
            "language",
            "publisher",
            "imprint",
            "series.sort_name",
            "volume.number",
            "volume.number_to",
            "issue",
        ),
    )
    review = StringField()
    rights = StringField()
    scan_info = StringField()
    series = SimpleNamedNestedField(schema=SeriesSchema)
    series_groups = StringSetField()
    store_date = DateField()
    stories = SimpleNamedDictField(sort=False)
    summary = StringField()
    tagger = StringField()
    tags = SimpleNamedDictField()
    teams = SimpleNamedDictField()
    universes = SimpleNamedDictField(values=Nested(UniverseSchema))
    updated_at = DateTimeField()
    volume = SimpleNamedNestedField(
        schema=VolumeSchema, field=IntegerField, name_key=NUMBER_KEY, primitive_type=int
    )
    year = IntegerField()


class ComicboxSchemaMixin:
    """Mixin for comicbox schemas."""

    ROOT_TAG = "comicbox"
    WRAP_TAGS = ROOT_TAG
    HAS_PAGE_COUNT = True
