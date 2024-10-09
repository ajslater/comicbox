"""Marshmallow pycountry fields."""

from abc import ABC
from logging import getLogger

import pycountry
from marshmallow import fields

from comicbox.fields.fields import DeserializeMeta, StringField

LOG = getLogger(__name__)


class PyCountryField(fields.String, ABC, metaclass=DeserializeMeta):
    """A pycountry value."""

    MODULE = None

    def __init__(self, *args, serialize_name=False, **kwargs):
        """Optionally serialize with full names."""
        self._serialize_name = serialize_name
        super().__init__(*args, **kwargs)

    @staticmethod
    def _clean_name(name_obj):
        if not name_obj:
            return None
        name: str | None = StringField().deserialize(name_obj)  # type: ignore
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

            if len(name) == 2:  # noqa PLR2004
                # Language lookup fails for 'en' unless alpha_2 is specified.
                obj = cls.MODULE.get(alpha_2=name)  # type: ignore
            else:
                obj = cls.MODULE.lookup(name)  # type: ignore
        except Exception as exc:
            LOG.warning(exc)
            obj = None

        if obj is None:
            LOG.warning(f"Couldn't find {tag} for {name}")

        return obj

    @staticmethod
    def _to_alpha_code(pc_obj):
        lang_code = None
        try:
            try:
                lang_code = pc_obj.alpha_2
            except AttributeError:
                lang_code = pc_obj.alpha_3
        except AttributeError:
            LOG.warning(f"No alpha 2 or alpha 3 code for {pc_obj}")
        return lang_code

    def _deserialize(self, value, attr, *_args, **_kwargs):
        """Return the alpha 2 encoding."""
        lang_code = None
        if pc_obj := self._get_pycountry(attr, value):
            lang_code = self._to_alpha_code(pc_obj)
        return lang_code

    def _serialize(self, value, attr, *_args, **_kwargs):
        """Return the long name."""
        lang_code = None
        if pc_obj := self._get_pycountry(attr, value):
            if self._serialize_name:
                lang_code = pc_obj.name
            else:
                lang_code = self._to_alpha_code(pc_obj)
        return lang_code


class LanguageField(PyCountryField):
    """PyCountry Language Field."""

    MODULE = pycountry.languages


class CountryField(PyCountryField):
    """PyCountry Country Field."""

    MODULE = pycountry.countries
