"""Xml versions of fields."""

from collections.abc import Mapping

from marshmallow.fields import Field, Nested
from marshmallow_union import Union
from typing_extensions import override

from comicbox.fields.collection_fields import (
    EmbeddedStringSetField,
    IntegerListField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
    ComicInfoMangaField,
    EnumField,
    OriginalFormatField,
    ReadingDirectionField,
    YesNoField,
)
from comicbox.fields.fields import IssueField, StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pdf import PdfDateTimeField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.fields.union import UNION_SCHEMA_IGNORE_ERRORS
from comicbox.schemas.base import BaseSubSchema

CDATA_KEY = "#text"


def get_cdata(value):
    """Return the cdata value if it exists or the whole value."""
    if isinstance(value, Mapping):
        return value.get(CDATA_KEY)
    return value


class CDataFieldMixin:
    """Get value or cdata."""

    def _deserialize(self, value, *args, **kwargs):
        value = get_cdata(value)
        return super()._deserialize(value, *args, **kwargs)  # pyright: ignore[reportAttributeAccessIssue]


# FIELDS
class XmlStringField(StringField, CDataFieldMixin):
    """Get value or cdata."""


class XmlIssueField(IssueField, CDataFieldMixin):
    """Get value or cdata."""


# DATETIME
class XmlDateField(DateField, CDataFieldMixin):
    """Get value or cdata."""


class XmlDateTimeField(DateTimeField, CDataFieldMixin):
    """Get value or cdata."""


class XmlPdfDateTimeField(PdfDateTimeField, CDataFieldMixin):
    """Get value or cdata."""


# ENUM
class XmlEnumField(EnumField, CDataFieldMixin):
    """Get value or cdata."""


class XmlReadingDirectionField(ReadingDirectionField, CDataFieldMixin):
    """Get value or cdata."""


class XmlOriginalFormatField(OriginalFormatField, CDataFieldMixin):
    """Get value or cdata."""


class XmlComicInfoMangaField(ComicInfoMangaField, CDataFieldMixin):
    """Get value or cdata."""


class XmlYesNoField(YesNoField, CDataFieldMixin):
    """Get value or cdata."""


# NUMBERS


class XmlBooleanField(BooleanField, CDataFieldMixin):
    """Get value or cdata."""

    @override
    def _serialize(self, *args, **kwargs) -> str | None:
        # xml booleans are lowercase
        result = super()._serialize(*args, **kwargs)
        return result if result is None else str(result).lower()


class XmlIntegerField(IntegerField, CDataFieldMixin):
    """Get value or cdata."""


class XmlDecimalField(DecimalField, CDataFieldMixin):
    """Get value or cdata."""


# PYCOUNTRY


class XmlCountryField(CountryField, CDataFieldMixin):
    """Get value or cdata."""


class XmlLanguageField(LanguageField, CDataFieldMixin):
    """Get value or cdata."""


# COLLECTIONS


class XmlListFieldMixin:
    """Get value or cdata."""

    @staticmethod
    def get_tag_value(value):
        """Get data for the tag value."""
        return get_cdata(value)


class XmlListField(XmlListFieldMixin, ListField):
    """XML List Field."""


class XmlStringListField(XmlListFieldMixin, StringListField):
    """XML String List Field."""


class XmlStringSetField(XmlListFieldMixin, StringSetField):
    """XML String Set Field."""

    FIELD = XmlStringField


class XmlEmbeddedStringSetField(XmlListFieldMixin, EmbeddedStringSetField):
    """XML Embedded String Set Field."""

    FIELD = XmlStringField


class XmlIntegerListField(XmlListFieldMixin, IntegerListField):
    """XML Integer List Field."""

    FIELD = XmlIntegerField


def create_sub_tag_field(
    sub_tag: str,
    field: Field,
) -> Nested:
    """Create a nested single schema, common to xml schemas."""
    sub_tag_schema_name = sub_tag + "Schema"
    sub_tag_schema_class = type(sub_tag_schema_name, (BaseSubSchema,), {sub_tag: field})
    return Nested(sub_tag_schema_class)


def xml_polyfield(schema_class: type[BaseSubSchema], field: Field) -> Union:
    """Get a Union of nested schemas and fields."""
    return Union(
        [
            # First field is the serialize type
            Nested(schema_class(ignore_errors=UNION_SCHEMA_IGNORE_ERRORS)),
            field,
        ]
    )


def xml_list_polyfield(
    schema_class: type[BaseSubSchema],
    field: Field,
    sort_keys: tuple[str, ...] = ("#text",),
    **kwargs,
) -> ListField:
    """Get a List of unions."""
    union_field = xml_polyfield(schema_class, field)
    return ListField(union_field, sort_keys=sort_keys, **kwargs)
