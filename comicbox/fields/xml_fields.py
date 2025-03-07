"""Xml versions of fields."""

from collections.abc import Mapping
from functools import wraps

from comicbox.fields.collection_fields import (
    IntegerListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum_fields import (
    AgeRatingField,
    MangaField,
    OriginalFormatField,
    ReadingDirectionField,
    YesNoField,
)
from comicbox.fields.fields import IssueField, StringField
from comicbox.fields.number_fields import BooleanField, DecimalField, IntegerField
from comicbox.fields.pycountry import CountryField, LanguageField
from comicbox.fields.time_fields import DateField


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


# TIME
class XmlDateField(DateField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


# ENUM
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


class XmlAgeRatingField(AgeRatingField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlMangaField(MangaField):
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


class XmlStringListField(StringListField):
    """Check for cdata."""

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlStringSetField(StringSetField):
    """Check for cdata."""

    FIELD = XmlStringField

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)


class XmlIntegerListField(IntegerListField):
    """Check for cdata."""

    FIELD = XmlIntegerField

    @cdata
    def _deserialize(self, *args, **kwargs):
        return super()._deserialize(*args, **kwargs)
