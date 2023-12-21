"""Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""
from typing import Union

from comicfn2dict import comicfn2dict, dict2comicfn
from marshmallow.fields import Nested

from comicbox.fields.collections import StringListField
from comicbox.fields.fields import StringField
from comicbox.fields.numbers import IntegerField
from comicbox.schemas.base import BaseSchema, BaseSubSchema
from comicbox.schemas.comicbox_mixin import (
    ISSUE_COUNT_KEY,
    ISSUE_KEY,
    ROOT_TAG,
    SERIES_KEY,
    VOLUME_KEY,
)

SERIES_TAG = SERIES_KEY
VOLUME_TAG = VOLUME_KEY
ISSUE_COUNT_TAG = ISSUE_COUNT_KEY
ISSUE_TAG = ISSUE_KEY


class FilenameRenderModule:
    """Filename Render module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to filename string."""
        data = obj.get(FilenameSchema.ROOT_TAGS[0])
        return dict2comicfn(data, *args, **kwargs)

    @staticmethod
    def loads(s: Union[bytes, str], *args, **kwargs):
        """Load filename to dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            sub_data = comicfn2dict(cleaned_s, *args, **kwargs)
            return {FilenameSchema.ROOT_TAGS[0]: sub_data}
        return None


class FilenameSubSchema(BaseSubSchema):
    """File name sub schema."""

    ext = StringField()
    issue = StringField()
    issue_count = IntegerField(minimum=0)
    original_format = StringField()
    remainders = StringListField()
    series = StringField()
    scan_info = StringField()
    title = StringField()
    volume = IntegerField()
    year = IntegerField()


class FilenameSchema(BaseSchema):
    """File name schema."""

    CONFIG_KEYS = frozenset({"fn", "filename"})
    FILENAME = "comicbox-filename.txt"
    ROOT_TAGS = (ROOT_TAG,)

    comicbox = Nested(FilenameSubSchema)

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = FilenameRenderModule
