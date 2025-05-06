"""Export comicbox.schemas to comicapi metadata."""

# https://github.com/comictagger/comictagger/blob/develop/comicapi/genericmetadata.py
from decimal import Decimal
from types import MappingProxyType

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import ListField, StringListField, StringSetField
from comicbox.fields.comicinfo import ComicInfoAgeRatingField
from comicbox.fields.enum_fields import ComicInfoMangaField, YesNoField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicbookinfo import ComicBookInfoCreditSchema
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema

ISSUE_ID_TAG = "issue_id"
SERIES_ID_TAG = "series_id"
IS_VERSION_OF_TAG = "is_version_of"
IDENTIFIER_TAG = "identifier"
STORY_ARC_TAG = "story_arcs"
PAGES_TAG = "pages"
INDEX_TAG = "Image"
SERIES_ALIASES_TAG = "series_aliases"
TITLE_ALIASES_TAG = "title_aliases"
BOOKMARK_ATTRIBUTE = "Bookmark"
IMAGE_ATTRIBUTE = "Image"
DATA_ORIGIN_TAG = "data_origin"


class DataOriginSchema(BaseSubSchema):
    """Comictagger Tag Origin."""

    name = StringField()

    class Meta(BaseSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType({"id": StringField()})


class ComictaggerPageInfoSchema(BaseSchema):
    """Comictagger Page Info data structure."""

    Type = StringField()
    Bookmark = StringField()
    DoublePage = BooleanField()
    Image = IntegerField()
    ImageSize = IntegerField(minimum=0)
    ImageHeight = IntegerField(minimum=0)
    ImageWidth = IntegerField(minimum=0)


class ComictaggerSubSchema(JsonSubSchema):
    """Comictagger schema."""

    # comictagger unique
    data_origin = Nested(DataOriginSchema)
    issue_id = StringField()
    series_id = StringField()

    # comicinfo, comicbookinfo & comet
    series = StringField()
    series_aliases = StringSetField()
    issue = StringField()
    title = StringField()
    publisher = StringField()
    month = IntegerField(minimum=0, maximum=12)
    year = IntegerField()
    day = IntegerField(minimum=0, maximum=31)
    issue_count = IntegerField(minimum=0)
    volume = IntegerField()
    genres = StringSetField()
    language = LanguageField()
    description = StringField()

    volume_count = IntegerField(minimum=0)
    critical_rating = DecimalField()
    country = CountryField()

    alternate_series = StringField()
    alternate_number = IntegerField()
    alternate_count = IntegerField()
    imprint = StringField()
    notes = StringField()
    web_link = StringSetField(as_string=True)
    # format in include
    manga = ComicInfoMangaField()
    black_and_white = YesNoField()
    page_count = IntegerField(minimum=0)
    maturity_rating = ComicInfoAgeRatingField()

    story_arcs = StringListField(sort=False)
    series_groups = StringSetField()
    scan_info = StringField()

    characters = StringSetField()
    teams = StringSetField()
    locations = StringSetField()

    alternate_images = StringListField(sort=False)
    # credits in include
    tags = StringSetField()
    pages = ListField(Nested(ComictaggerPageInfoSchema), sort_keys=(INDEX_TAG,))

    # comet unique
    price = DecimalField(minimum=Decimal("0.0"))
    is_version_of = StringSetField(as_string=True)
    rights = StringField()
    identifier = StringSetField(as_string=True)
    last_mark = StringField()
    cover_image = StringField()

    class Meta(JsonSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "format": StringField(),
                "credits": ListField(
                    Nested(ComicBookInfoCreditSchema),
                    sort_keys=("person", "role", "primary"),
                ),
            }
        )


class ComictaggerSchema(JsonSchema):
    """Comictagger Schema."""

    ROOT_TAG: str = "comictagger"
    ROOT_KEYPATH: str = ROOT_TAG
    HAS_PAGE_COUNT: bool = True
    HAS_PAGES: bool = True

    comictagger = Nested(ComictaggerSubSchema)
