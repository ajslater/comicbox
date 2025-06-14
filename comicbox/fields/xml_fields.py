"""Xml versions of fields."""

from collections.abc import Mapping
from functools import wraps

from marshmallow import fields
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


def get_cdata(value):
    """Return the cdata value if it exists or the whole value."""
    if isinstance(value, Mapping):
        return value.get("#text")
    return value


def cdata(func):
    """Get #text cdata from xml dicts."""

    @wraps(func)
    def wrapper(self, value, *args, **kwargs):
        value = get_cdata(value)
        return func(self, value, *args, **kwargs)

    return wrapper


# FIELDS
class XmlStringField(StringField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlIssueField(IssueField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# DATETIME
class XmlDateField(DateField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlDateTimeField(DateTimeField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlPdfDateTimeField(PdfDateTimeField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# ENUM
class XmlEnumField(EnumField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlReadingDirectionField(ReadingDirectionField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlOriginalFormatField(OriginalFormatField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlComicInfoMangaField(ComicInfoMangaField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlYesNoField(YesNoField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# NUMBERS


class XmlBooleanField(BooleanField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlBooleanAttributeField(BooleanField):
    """Fix xmltodict bug: https://github.com/martinblech/xmltodict/pull/310."""

    @override
    def _serialize(self, *args, **kwargs) -> str | None:
        result = super()._serialize(*args, **kwargs)
        return result if result is None else str(result).lower()


class XmlIntegerField(IntegerField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlDecimalField(DecimalField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlTextDecimalField(XmlDecimalField):
    """Fix bug in xmltodict."""

    @override
    def _serialize(self, value, attr, obj, **kwargs):
        """Fix bug in xmltodict."""
        # https://github.com/martinblech/xmltodict/issues/366
        result = super()._serialize(value, attr, obj, **kwargs)
        return str(result)


# PYCOUNTRY


class XmlCountryField(CountryField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlLanguageField(LanguageField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# COLLECTIONS


class XmlListFieldMixin:
    """Check for cdata."""

    @staticmethod
    def get_tag_value(value):
        """Get data for the tag value."""
        return get_cdata(value)


class XmlListField(XmlListFieldMixin, ListField):
    """Check for cdata."""


class XmlStringListField(XmlListFieldMixin, StringListField):
    """Check for cdata."""

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlStringSetField(XmlListFieldMixin, StringSetField):
    """Check for cdata."""

    FIELD: fields.Field = XmlStringField  # pyright: ignore[reportAssignmentType]

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlEmbeddedStringSetField(XmlListFieldMixin, EmbeddedStringSetField):
    """Check for cdata."""

    FIELD: fields.Field = XmlStringField  # pyright: ignore[reportAssignmentType]·

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlIntegerListField(XmlListFieldMixin, IntegerListField):
    """Check for cdata."""

    FIELD: fields.Field = XmlIntegerField  # pyright: ignore[reportAssignmentType]·

    @override
    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


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
