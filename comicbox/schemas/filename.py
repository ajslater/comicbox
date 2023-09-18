"""Parse comic book archive names using the simple 'parse' parser.

A more sophisticaed library like pyparsing or rebulk might be able to
build a faster, more powerful matching engine with fewer parsers with
optional fields. But this brute force method with the parse library is
effective, simple and easy to read and to contribute to.
"""

from types import MappingProxyType
from typing import Union

from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_base import ComicboxBaseSchema
from comicfn2dict import comicfn2dict


class FilenameRenderModule:
    """Filename Render module."""

    @staticmethod
    def dumps(obj: dict, *args, **kwargs):
        """Dump dict to filename string."""
        data = sub_data if (sub_data := obj.get(FilenameSchema.ROOT_TAG)) else obj
        return comicfn2dict.unparse(data, *args, **kwargs)

    @staticmethod
    def loads(s: Union[bytes, str], *args, **kwargs):
        """Load filename to dict."""
        cleaned_s = StringField().deserialize(s)
        if cleaned_s:
            return comicfn2dict.parse(cleaned_s, *args, **kwargs)
        return None


FN_DATA_KEY_MAP = MappingProxyType(
    {
        "ext": "ext",
        "issue": "issue",
        "issue_count": "issue_count",
        "original_format": "original_format",
        "remainders": "remainders",
        "series": "series",
        "scan_info": "scan_info",
        "title": "title",
        "volume": "volume",
        "year": "year",
    }
)


class FilenameSchema(ComicboxBaseSchema):
    """File name schema."""

    DATA_KEY_MAP = FN_DATA_KEY_MAP
    ROOT_TAG = "filename"
    ROOT_TAGS = MappingProxyType({ROOT_TAG: {}})
    CONFIG_KEYS = frozenset({"fn", "filename"})
    FILENAME = "comicbox-filename.txt"

    class Meta(ComicboxBaseSchema.Meta):
        """Schema Options."""

        fields = ComicboxBaseSchema.Meta.create_fields(FN_DATA_KEY_MAP)
        render_module = FilenameRenderModule
