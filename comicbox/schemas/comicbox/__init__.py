"""Mixin for Comicbox Schemas."""

from decimal import Decimal
from inspect import isclass
from types import MappingProxyType

from marshmallow import Schema
from marshmallow.fields import Field, Nested
from marshmallow_union import Union

from comicbox.fields.collection_fields import (
    DictField,
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
LAST_MARK_KEY = "last_mark"
LANGUAGE_KEY = "language"
LOCATIONS_KEY = "locations"
MANGA_KEY = "manga"
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
PAGE_TYPE_KEY = "page_type"
PAGE_INDEX_KEY = "index"  # only used in transform
PAGE_KEYS = frozenset(
    {PAGE_TYPE_KEY, "bookmark", "height", "width", "double_page", "key", "size"}
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


class IdentifierSchema(BaseSubSchema):  # Comet, CIX, CT, Metron
    """Identifier schema."""

    nss = StringField()
    url = StringField()


class IdentifiedSchema(BaseSubSchema):  # Metron ONLY
    """Identified Schema."""

    identifiers = DictField(values=Nested(IdentifierSchema))


class IdentifiedNameSchema(IdentifiedSchema):  # Comicbox
    """Named Element with an identifier."""

    name = StringField()


class SimpleNamedDictField(Union):
    """A dict that also accepts a simple string set and builds a dict from that."""

    def __init__(
        self,
        *args,
        keys: Field | type[Field] = StringField,
        values: Field | type[Field] | None = None,
        allow_empty_values: bool = True,
        **kwargs,
    ):
        """Create the union."""
        if values is None:
            values = Nested(IdentifiedSchema)
        fields = [
            DictField(keys=keys, values=values, allow_empty_values=allow_empty_values),
            StringSetField(),
        ]
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


class PersonSchema(IdentifiedSchema):
    """Credit Person Schema."""

    roles = SimpleNamedDictField(  # Comet, CIX, CBI, Metron
        keys=RoleField, allow_empty_values=True
    )


class PageInfoSchema(BaseSubSchema):  # CIX, CT - ONLY
    """Comicbox page info schema."""

    bookmark = StringField()
    double_page = BooleanField()
    key = StringField()
    width = IntegerField(minimum=0)
    height = IntegerField(minimum=0)
    size = IntegerField(minimum=0)
    page_type = PageTypeField()


class SeriesSchema(IdentifiedNameSchema):
    """Series Schema."""

    sort_name = StringField()  # Metron ONLY
    start_year = IntegerField()  # Metron ONLY
    volume_count = IntegerField(minimum=0)  # CBI, CT, Metron


class VolumeSchema(IdentifiedSchema):
    """Volume Schema."""

    issue_count = IntegerField(minimum=0)  # CBI, CT, CIX, Filename, Metron
    number = IntegerField(minimum=0)  # All
    number_to = IntegerField(minimum=0)  # Metron ONLY


class IssueSchema(BaseSubSchema):
    """Issue Schema."""

    name = StringField()  # All
    number = DecimalField()  # Comicbox
    suffix = StringField()  # Comicbox


class ReprintSchema(IdentifiedSchema):
    """Schema for Reprints of this issue."""

    language = LanguageField()  # Metron ONLY
    series = Nested(SeriesSchema)  # Comet, CIX, CT
    volume = Nested(VolumeSchema)  # Comet, CIX, CT, Metron
    issue = StringField()  # Comet, CIX, CT, Metron


class IdentifierPrimarySource(BaseSubSchema):
    """Identifiers Primary Source."""

    nid = StringField(required=True)  # Metron ONLY
    url = StringField()  # Comicbox


class UniverseSchema(IdentifiedSchema):
    """Universe Schema."""

    designation = StringField()  # Metron ONLY


class ArcSchema(IdentifiedSchema):
    """Story Arc Schema."""

    number = IntegerField()  # CIX, Metron


class DateSchema(BaseSubSchema):
    """Date Schema."""

    cover_date = DateField()  # Comet, PDF, Metron
    store_date = DateField()  # Metron ONLY
    year = IntegerField()  # CIX, CBI, CT, Filename, Metron
    month = IntegerField(minimum=1, maximum=12)  # CBI, CIX, CT
    day = IntegerField(minimum=1, maximum=31)  # CBI, CIX


class PagesField(DictField):  # CIX ONLY, CT
    """ComicInfo Pages."""

    def __init__(self, *args, keys_as_string=False, **kwargs):
        """ComicInfo Pages with keys_as_string option."""
        super().__init__(
            *args,
            keys=IntegerField(minimum=0, as_string=keys_as_string),
            values=Nested(PageInfoSchema),
            case_insensitive=False,
            **kwargs,
        )


class ComicboxSubSchemaMixin(IdentifiedSchema):
    """Mixin for Comicbox Sub Schemas."""

    age_rating = AgeRatingField()  # CIX, Metron
    alternate_images = StringSetField()  # CT ONLY
    arcs = SimpleNamedDictField(values=Nested(ArcSchema))  # CIX, CT, Metron
    characters = SimpleNamedDictField()  # Comet, CIX, CT, Metron
    credits = SimpleNamedDictField(  # Comet, CIX, CBI, Metron
        values=Nested(PersonSchema)
    )
    credit_primaries = DictField(values=DictField)  # CBI ONLY
    country = CountryField()  # CBI, CIX, CT, Metron
    collection_title = StringField()  # Metron ONLY
    cover_image = StringField()  # Comet ONLY, CT
    critical_rating = DecimalField(places=2)  # CBI, CIX
    date = Nested(DateSchema)
    ext = StringField()  # Filename ONLY
    original_format = OriginalFormatField()  # Comet, CT, Filename, CIX, Metron
    genres = SimpleNamedDictField()  # Comet, CBI, CIX, CT, Metron, PDF
    # identifiers from parent # Comet, CBI, CIX, CT, Metron,
    identifier_primary_source = Nested(IdentifierPrimarySource)  # Metron
    issue = Nested(IssueSchema)  # ALL
    imprint = SimpleNamedNestedField()  # CIX, CT, Metron
    language = LanguageField()  # Comet, CBI, CIX, CT, Metron
    last_mark = IntegerField(minimum=0)  # Comet ONLY, CT
    locations = SimpleNamedDictField()  # CIX, CT, Metron
    manga = ComicInfoMangaField()  # CIX ONLY
    monochrome = BooleanField()  # CIX ONLY, CT
    notes = StringField()  # CT, Metron, CIX
    page_count = IntegerField(minimum=0)  # CIX, Comet, Metron, CBI
    pages = PagesField()  # CIX ONLY, CT
    publisher = SimpleNamedNestedField()  # Comet, CIX, CT, Metron
    prices = DictField(  # Comet, CT, Metron
        keys=CountryField(allow_empty=True),
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
            "publisher",
            "imprint",
            "series.sort_name",
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
    series_groups = StringSetField()  # CIX ONLY, CT
    stories = SimpleNamedDictField(sort=False)  # CBI, CT, Metron, PDF
    summary = StringField()  # Comet, CIX, CT, CBI, Metron
    tagger = StringField()  # CBI, PDF
    tags = SimpleNamedDictField()  # CBI, CT, Metron
    teams = SimpleNamedDictField()  # CIX, Metron, CT
    universes = SimpleNamedDictField(values=Nested(UniverseSchema))  # Metron ONLY
    updated_at = DateTimeField()  # CBI, Metron, PDF
    volume = SimpleNamedNestedField(  # Comet, CBI, CIX, Filename, Metron
        schema=VolumeSchema, field=IntegerField, name_key=NUMBER_KEY, primitive_type=int
    )


class ComicboxSchemaMixin:
    """Mixin for comicbox schemas."""

    ROOT_TAG = "comicbox"
    ROOT_KEY_PATH = ROOT_TAG
    HAS_PAGE_COUNT = True
