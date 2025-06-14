"""A class to encapsulate the ComicBookInfo data."""

# https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki
from types import MappingProxyType

from marshmallow import Schema
from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import ListField, StringSetField
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import BooleanField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateTimeField
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema

LAST_MODIFIED_TAG = "lastModified"
ROLE_TAG = "role"
PERSON_TAG = "person"
CREDITS_TAG = "credits"
PRIMARY_TAG = "primary"


class ComicBookInfoCreditSchema(Schema):
    """ComicBookInfo Credit Schema."""

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
            {
                CREDITS_TAG: ListField(
                    Nested(ComicBookInfoCreditSchema),
                    sort_keys=("person", "role", "primary"),
                )
            }
        )


class ComicBookInfoSchema(JsonSchema):
    """ComicBookInfo JSON schema."""

    ROOT_DATA_KEY: str = "ComicBookInfo/1.0"
    ROOT_TAG: str = "ComicBookInfo"
    ROOT_KEYPATH: str = ROOT_TAG
    TAG_ORDER: tuple[str, ...] = ("appID", "lastModified", ROOT_DATA_KEY, "schema")
    HAS_PAGE_COUNT: bool = True

    appID = StringField()  # noqa: N815
    lastModified = DateTimeField()  # noqa: N815
    ComicBookInfo = Nested(ComicBookInfoSubSchema, data_key=ROOT_DATA_KEY)
    schema = Constant(
        "https://github.com/ajslater/comicbox/blob/main/schemas/comic-book-info-v1.0.schema.json"
    )
