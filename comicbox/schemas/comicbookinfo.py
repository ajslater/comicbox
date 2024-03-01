"""A class to encapsulate the ComicBookInfo data."""

# https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki
from logging import getLogger
from types import MappingProxyType

from marshmallow import Schema, post_dump, post_load
from marshmallow.decorators import pre_dump, pre_load
from marshmallow.fields import Constant, Nested

from comicbox.fields.collections import StringSetField
from comicbox.fields.fields import StringField
from comicbox.fields.numbers import BooleanField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time import DateTimeField
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.json import JsonSchema, JsonSubSchema
from comicbox.version import VERSION

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


class ComicBookInfoCreditSchema(Schema):
    """ComicBookInfo Credit Dict Schema."""

    role = StringField()
    person = StringField()
    primary = BooleanField()


class ComicBookInfoSubSchema(JsonSubSchema):
    """ComicBookInfo JSON schema."""

    comments = StringField()
    country = CountryField(serialize_name=True)
    genre = StringSetField(as_string=True)
    issue = StringField()
    language = LanguageField(serialize_name=True)
    numberOfVolumes = IntegerField(minimum=0)  # noqa: N815
    numberOfIssues = IntegerField(minimum=0)  # noqa: N815
    pages = IntegerField(minimum=0)
    publicationDay = IntegerField(minimum=0, maximum=31)  # noqa: N815
    publicationMonth = IntegerField(minimum=0, maximum=12)  # noqa: N815
    publicationYear = IntegerField()  # noqa: N815
    publisher = StringField()
    rating = StringField()
    series = StringField()
    tags = StringSetField(as_string=True)
    title = StringField()
    volume = IntegerField()

    class Meta(JsonSubSchema.Meta):
        """Schema Options."""

        include = MappingProxyType(
            {CREDITS_TAG: Nested(ComicBookInfoCreditSchema, many=True)}
        )


class ComicBookInfoSchema(JsonSchema):
    """ComicBookInfo JSON schema."""

    ROOT_TAGS = ("ComicBookInfo/1.0",)
    CONFIG_KEYS = frozenset({"cbi", "cbl", "comicbookinfo", "comicbooklover"})
    FILENAME = "comic-book-info.json"

    _ROOT_TAG = ROOT_TAGS[0]
    _ROOT_KEY = "root"

    appID = Constant(f"comicbox/{VERSION}")  # noqa: N815
    lastModified = DateTimeField()  # noqa: N815
    schema = Constant(
        "https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki"
    )
    root = Nested(ComicBookInfoSubSchema)

    @staticmethod
    def _move_tag_to_another(data, tag_a, tag_b):
        """Move one tag to another."""
        if tag_a in data:
            data = dict(data)
            if root := data.pop(tag_a, None):
                data[tag_b] = root
            return MappingProxyType(data)
        return data

    @trap_error(pre_load)
    def move_dot_tag_to_root_key_load(self, data, **_kwargs):
        """Hack around the dot delimiter before load."""
        data = super().validate_root_tag(data)
        if not data:
            return data
        return self._move_tag_to_another(data, self._ROOT_TAG, self._ROOT_KEY)

    def validate_root_tag(self, data, **_kwargs):
        """Move this check into the mover method above."""
        return data

    @trap_error(post_load)
    def move_root_key_to_dot_tag_load(self, data, **_kwargs):
        """Hack around the dot delimiter after load."""
        return self._move_tag_to_another(data, self._ROOT_KEY, self._ROOT_TAG)

    @pre_dump
    def move_dot_tag_to_root_key_dump(self, data, **_kwargs):
        """Hack around the dot delimiter before dump."""
        return self._move_tag_to_another(data, self._ROOT_TAG, self._ROOT_KEY)

    @post_dump
    def move_root_key_to_dot_tag_dump(self, data, **_kwargs):
        """Hack around the dot delimiter after dump."""
        return self._move_tag_to_another(data, self._ROOT_KEY, self._ROOT_TAG)
