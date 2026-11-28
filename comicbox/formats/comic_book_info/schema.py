"""A class to encapsulate the ComicBookInfo data."""

# https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki
import sys
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from marshmallow import Schema
from marshmallow.fields import Constant, Nested

from comicbox.formats.base.fields.collection_fields import ListField, StringSetField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import BooleanField, IntegerField
from comicbox.formats.base.fields.pycountry import CountryField, LanguageField
from comicbox.formats.base.fields.time_fields import DateTimeField
from comicbox.formats.base.schemas.json_schemas import JsonSchema, JsonSubSchema

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

LAST_MODIFIED_TAG = "lastModified"
ROLE_TAG = "role"
PERSON_TAG = "person"
CREDITS_TAG = "credits"
PRIMARY_TAG = "primary"


class ComicBookInfoIssueField(StringField):
    """
    CBI's issue: an integer, read liberally.

    A JSON integer, or a whole float, is that integer. Any other value is
    text the shared issue parse splits as it does every format's, so "1/2"
    is 0.5 and "1.5" is 1.5, not 1. The transform writes a whole integer or
    nothing.
    """

    @override
    def _deserialize(self, value: Any, *args: Any, **kwargs: Any) -> int | str:
        if isinstance(value, float | Decimal) and value == int(value):
            value = int(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return super()._deserialize(value, *args, **kwargs)

    @override
    def _serialize(self, value: Any, *_args: Any, **_kwargs: Any) -> Any:
        return value


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
    issue = ComicBookInfoIssueField()
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
