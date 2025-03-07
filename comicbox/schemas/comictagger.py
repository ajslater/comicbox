"""Export comicbox.schemas to comicapi metadata."""

# https://github.com/comictagger/comictagger/blob/develop/comicapi/genericmetadata.py
from decimal import Decimal
from types import MappingProxyType

from marshmallow.fields import Nested

from comicbox.fields.collection_fields import StringListField, StringSetField
from comicbox.fields.enum_fields import AgeRatingField, MangaField, YesNoField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicbookinfo import ComicBookInfoCreditSchema
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema

TAG_ORIGIN_KEY = "tag_origin"
ISSUE_ID_KEY = "issue_id"
SERIES_ID_KEY = "series_id"
IS_VERSION_OF_TAG = "is_version_of"
IDENTIFIER_TAG = "identifier"
STORY_ARC_TAG = "story_arcs"
PAGES_TAG = "pages"
INDEX_TAG = "Image"


class TagOriginSchema(BaseSubSchema):
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
    tag_origin = Nested(TagOriginSchema())
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
    web_link = StringField()
    # format in include
    manga = MangaField()
    black_and_white = YesNoField()
    page_count = IntegerField(minimum=0)
    maturity_rating = AgeRatingField()

    story_arcs = StringListField(sort=False)
    series_groups = StringSetField()
    scan_info = StringField()

    characters = StringSetField()
    teams = StringSetField()
    locations = StringSetField()

    alternate_images = StringListField(sort=False)
    # credits in include
    tags = StringSetField()
    pages = Nested(ComictaggerPageInfoSchema, many=True)

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
                "credits": Nested(ComicBookInfoCreditSchema, many=True),
            }
        )


class ComictaggerSchema(JsonSchema):
    """Comictagger Schema."""

    CONFIG_KEYS = frozenset({"comictagger", "ct"})
    FILENAME = "comictagger.json"
    ROOT_TAGS = ("comictagger",)

    comictagger = Nested(ComictaggerSubSchema)
