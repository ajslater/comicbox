"""Xml versions of fields."""

from collections.abc import Mapping
from functools import wraps

from comicbox.fields.collection_fields import (
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

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlIssueField(IssueField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# DATETIME
class XmlDateField(DateField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlDateTimeField(DateTimeField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlPdfDateTimeField(PdfDateTimeField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# ENUM
class XmlEnumField(EnumField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlReadingDirectionField(ReadingDirectionField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlOriginalFormatField(OriginalFormatField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlComicInfoMangaField(ComicInfoMangaField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlYesNoField(YesNoField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# NUMBERS


class XmlBooleanField(BooleanField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlBooleanAttributeField(BooleanField):
    """Fix xmltodict bug: https://github.com/martinblech/xmltodict/pull/310."""

    def _serialize(self, *args, **kwargs) -> str | None:  # type: ignore[reportIncompatibleMethodOverride]
        result = super()._serialize(*args, **kwargs)
        return result if result is None else str(result).lower()


class XmlIntegerField(IntegerField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlDecimalField(DecimalField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# PYCOUNTRY


class XmlCountryField(CountryField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlLanguageField(LanguageField):
    """Check for cdata."""

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

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlStringSetField(XmlListFieldMixin, StringSetField):
    """Check for cdata."""

    FIELD = XmlStringField

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlIntegerListField(XmlListFieldMixin, IntegerListField):
    """Check for cdata."""

    FIELD = XmlIntegerField

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)
