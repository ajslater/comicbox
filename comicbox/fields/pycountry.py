"""Marshmallow pycountry fields."""

from abc import ABC

import pycountry
from loguru import logger
from pycountry.db import Database
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta

_ALPHA_CODES = ("alpha_2", "alpha_3", "alpha_4", "name")


class PyCountryField(StringField, ABC, metaclass=TrapExceptionsMeta):
    """A pycountry value."""

    DB: Database = pycountry.countries
    EMPTY_CODE = ""

    def __init__(self, *args, serialize_name=False, allow_empty=False, **kwargs):
        """Optionally serialize with full names."""
        self._serialize_name = serialize_name
        self._allow_empty = allow_empty
        super().__init__(*args, **kwargs)

    @staticmethod
    def _clean_name(name_obj):
        if not name_obj:
            return None
        name: str | None = StringField().deserialize(name_obj)  # type: ignore[reportAssignmentType]
        if not name:
            return None
        return name.strip()

    @classmethod
    def _get_pycountry(cls, tag, name):
        """Get pycountry object for a country or language tag."""
        try:
            name = cls._clean_name(name)
            if not name:
                return None

            # Language lookup fails for 'en' unless alpha_2 is specified.
            obj = cls.DB.get(alpha_2=name) if len(name) == 2 else cls.DB.lookup(name)  # noqa: PLR2004
        except Exception as exc:
            logger.warning(exc)
            obj = None

        if obj is None:
            logger.warning(f"Couldn't find {tag} for {name}")

        return obj

    @classmethod
    def _to_alpha_code(cls, pc_obj):
        code = cls.EMPTY_CODE
        for attr in _ALPHA_CODES:
            if code := getattr(pc_obj, attr, cls.EMPTY_CODE):
                break
        return code

    @override
    def _deserialize(self, value, attr, *args, **kwargs):
        """Return the alpha 2 encoding."""
        value = super()._deserialize(value, attr, *args, **kwargs)
        code = self.EMPTY_CODE
        if pc_obj := self._get_pycountry(attr, value):
            code = self._to_alpha_code(pc_obj)
        return code

    @override
    def _serialize(self, value, attr, *args, **kwargs):
        """Return the long name."""
        value = super()._serialize(value, attr, *args, **kwargs)
        code = self.EMPTY_CODE
        if pc_obj := self._get_pycountry(attr, value):
            code = pc_obj.name if self._serialize_name else self._to_alpha_code(pc_obj)
        return code


class LanguageField(PyCountryField):
    """PyCountry Language Field."""

    DB: Database = pycountry.languages


class CountryField(PyCountryField):
    """PyCountry Country Field."""

    DB: Database = pycountry.countries
