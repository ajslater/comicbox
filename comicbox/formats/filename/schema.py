"""
Parse comic book archive names using the simple 'parse' parser.

A more sophisticated library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from typing import Any, Final

from comicfn2dict import comicfn2dict, dict2comicfn
from marshmallow.fields import Nested
from typing_extensions import override

from comicbox.formats.base.fields.collection_fields import StringListField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.formats.base.schemas.base import (
    BaseRenderModule,
    BaseSchema,
    BaseSubSchema,
)
from comicbox.formats.comicbox.schema import (
    ISSUE_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
)

SERIES_TAG = SERIES_KEY
VOLUME_TAG = VOLUME_KEY
ISSUE_COUNT_TAG = VOLUME_ISSUE_COUNT_KEY
ISSUE_TAG = ISSUE_KEY
_OTHER_SCHEMA_STARTS = ("<?", "<!")
_OTHER_SCHEMA_ENDS = ("{", ":")
# Characters a filename built from metadata can't safely hold, with their
# stand-ins. Path separators would turn the basename into a multi-component
# path and break rename/export. The rest are illegal on Windows and SMB
# shares; a renamed archive travels between systems, so they go on every
# platform. Left in, macOS's SMB client stores each as a private-use glyph
# (":" becomes U+F022) and Windows rejects them or reads ":" as an NTFS
# stream marker. Ordered: ": " before ":", so "Batman: Year One" reads back
# as one series while "Re:Zero" keeps its break as "Re-Zero".
_FILENAME_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("/", "_"),
    ("\\", "_"),
    (": ", " "),
    (":", "-"),
    *((char, "") for char in '"*<>?|'),
)


class FilenameRenderModule(BaseRenderModule):
    """Filename Render module."""

    @staticmethod
    def _sanitize(fn: str) -> str:
        """Replace characters so the result is a single portable filename."""
        for char, replacement in _FILENAME_REPLACEMENTS:
            fn = fn.replace(char, replacement)
        return fn

    @override
    @classmethod
    def dumps(cls, obj: dict, *args: Any, **kwargs: Any) -> str:
        """Dump dict to filename string."""
        data: dict = obj.get(FilenameSchema.ROOT_TAG, {})
        fn = dict2comicfn(data, *args, **kwargs)
        return cls._sanitize(fn)

    @staticmethod
    def _is_non_filename_format(s: str | bytes | bytearray) -> bool:
        """Detect if the input is xml, yaml or json."""
        if not s:
            return True
        t = str(s).split("\n")[0].strip().lower()
        return t.startswith(_OTHER_SCHEMA_STARTS) or t.endswith(_OTHER_SCHEMA_ENDS)

    @override
    @classmethod
    def loads(
        cls,
        s: str | bytes | bytearray,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, dict] | None:
        """Load filename to dict."""
        if cls._is_non_filename_format(s):
            return None

        if cleaned_s := cls.clean_string(s):
            sub_data = comicfn2dict(cleaned_s, *args, **kwargs)
            return {FilenameSchema.ROOT_TAG: sub_data}
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

    ROOT_TAG: str = "comicfn2dict"
    ROOT_KEYPATH: str = ROOT_TAG

    comicfn2dict = Nested(FilenameSubSchema)

    class Meta(BaseSchema.Meta):
        """Schema Options."""

        render_module = FilenameRenderModule
