"""A class to encapsulate the ComicBookInfo data."""

# https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki
from enum import Enum
from logging import getLogger
from types import MappingProxyType

from marshmallow import Schema
from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import StringSetField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateTimeField
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema

LOG = getLogger(__name__)

LAST_MODIFIED_TAG = "lastModified"
ROLE_TAG = "role"
PERSON_TAG = "person"
CREDITS_TAG = "credits"

ARTIST_TAG = "Artist"
COLORER_TAG = "Colorer"
COVER_ARTIST_TAG = "Cover Artist"
EDITOR_TAG = "Editor"
INKER_TAG = "Inker"
LETTERER_TAG = "Letterer"
OTHER_TAG = "Other"
PENCILLER_TAG = "Penciller"
WRITER_TAG = "Writer"


class ComicBookInfoRoleEnum(Enum):
    """ComicBookInfo Roles."""

    # Common but not restricted to
    ARTIST = "Artist"
    COLORER = "Colorer"
    COVER_ARTIST = "Cover Artist"
    EDITOR = "Editor"
    INKER = "Inker"
    LETTERER = "Letterer"
    OTHER = "Other"
    PENCILLER = "Penciller"
    TRANSLATOR = "Translator"
    WRITER = "Writer"


class ComicBookInfoCreditSchema(Schema):
    """ComicBookInfo Credit Dict Schema."""

    person = StringField()
    primary = BooleanField()
    role = StringField()


class ComicBookInfoSubSchema(JsonSubSchema):
    """ComicBookInfo JSON schema."""

    comments = StringField()
    country = CountryField(serialize_name=True)
    genre = StringSetField(as_string=True)
    issue = IntegerField()
    language = LanguageField(serialize_name=True)
    numberOfVolumes = IntegerField(minimum=0)  # noqa: N815
    numberOfIssues = IntegerField(minimum=0)  # noqa: N815
    pages = IntegerField(minimum=0)
    publicationDay = IntegerField(minimum=0, maximum=31)  # noqa: N815
    publicationMonth = IntegerField(minimum=0, maximum=12)  # noqa: N815
    publicationYear = IntegerField()  # noqa: N815
    publisher = StringField()
    rating = IntegerField()
    series = StringField()
    tags = StringSetField()
    title = StringField()
    volume = IntegerField()

    class Meta(JsonSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType(
            {CREDITS_TAG: Nested(ComicBookInfoCreditSchema, many=True)}
        )


class ComicBookInfoSchema(JsonSchema):
    """ComicBookInfo JSON schema."""

    ROOT_TAG = "ComicBookInfo/1.0"
    ROOT_KEY = "root"
    WRAP_TAGS = (ROOT_TAG,)
    CONFIG_KEYS = frozenset({"cbi", "cbl", "comicbookinfo", "comicbooklover"})
    FILENAME = "comic-book-info.json"
    TAG_ORDER = ("appID", "lastModified", ROOT_TAG, "schema")

    appID = StringField()  # noqa: N815
    lastModified = DateTimeField()  # noqa: N815
    root = Nested(ComicBookInfoSubSchema)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comic-book-info-v1.0.schema.json"
    )

    TAG_MOVE_MAP = MappingProxyType(
        {
            "pre_load": (ROOT_TAG, ROOT_KEY),
            "post_load": (ROOT_KEY, ROOT_TAG),
            "pre_dump": (ROOT_TAG, ROOT_KEY),
            "post_dump": (ROOT_KEY, ROOT_TAG),
        }
    )
