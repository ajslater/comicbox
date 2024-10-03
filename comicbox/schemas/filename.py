"""Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from comicfn2dict import comicfn2dict, dict2comicfn
from marshmallow import post_load
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
_OTHER_SCHEMA_STARTS = ("<?", "<!")
_OTHER_SCHEMA_ENDS = ("{", ":")


class FilenameRenderModule:
    """Filename Render module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to filename string."""
        data: dict = obj.get(FilenameSchema.ROOT_TAGS[0])  # type: ignore
        return dict2comicfn(data, *args, **kwargs)

    @staticmethod
    def _is_non_filename_format(s: str | bytes):
        """Detect if the input is xml, yaml or json."""
        t = str(s).split("\n")[0].strip().lower()
        return t.startswith(_OTHER_SCHEMA_STARTS) or t.endswith(_OTHER_SCHEMA_ENDS)

    @classmethod
    def loads(cls, s: bytes | str, *args, **kwargs):
        """Load filename to dict."""
        if not s:
            return None

        if cls._is_non_filename_format(s):
            return None

        cleaned_s: str | None = StringField().deserialize(s)  # type: ignore
        if not cleaned_s:
            return None

        sub_data = comicfn2dict(cleaned_s, *args, **kwargs)
        return {FilenameSchema.ROOT_TAGS[0]: sub_data}


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

    @post_load
    def validate_load(self, data, **_kwargs):
        """Make results with only remainders no result at all."""
        if len(data) == 1:
            data.pop("remainders", None)
        return data


class FilenameSchema(BaseSchema):
    """File name schema."""

    CONFIG_KEYS = frozenset({"fn", "filename"})
    FILENAME = "comicbox-filename.txt"
    ROOT_TAGS = (ROOT_TAG,)

    comicbox = Nested(FilenameSubSchema)

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = FilenameRenderModule

    @post_load
    def validate_load_data(self, data, **_kwargs):
        """If no data, return nothing."""
        if not data.get(ROOT_TAG):
            data = {}
        return data
