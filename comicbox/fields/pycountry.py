"""Marshmallow pycountry fields."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime

    import ruamel.yaml

from abc import ABC

import pycountry
from loguru import logger
from pycountry.db import Data, Database
from typing_extensions import override

from comicbox.fields.fields import StringField, TrapExceptionsMeta

_ALPHA_CODES = ("alpha_2", "alpha_3", "alpha_4", "name")


class PyCountryField(StringField, ABC, metaclass=TrapExceptionsMeta):
    """A pycountry value."""

    DB: Database = pycountry.countries
    EMPTY_CODE = ""

    def __init__(
        self: "PyCountryField|Any", *args: None, serialize_name: bool=False, allow_empty: bool=False, **kwargs: None
    ) -> None:
        """Optionally serialize with full names."""
        self._serialize_name = serialize_name
        self._allow_empty = allow_empty
        super().__init__(*args, **kwargs)

    @staticmethod
    def _clean_name(name_obj: str) -> str | None:
        if not name_obj:
            return None
        name: str | None = StringField().deserialize(name_obj)
        if not name:
            return None
        return name.strip()

    @classmethod
    def _get_pycountry(cls: "type[LanguageField|Any]", tag: str, name: str) -> Data | None:
        """Get pycountry object for a country or language tag."""
        try:
            name = cls._clean_name(name)
            if not name:
                return None

            # Language lookup fails for 'en' unless alpha_2 is specified.
            obj: Data | None = (
                cls.DB.get(alpha_2=name) if len(name) == 2 else cls.DB.lookup(name)  # noqa: PLR2004
            )
        except Exception as exc:
            logger.warning(exc)
            obj = None

        if obj is None:
            logger.warning(f"Couldn't find {tag} for {name}")

        return obj

    @classmethod
    def _to_alpha_code(cls: "type[LanguageField|Any]", pc_obj: Any) -> str:
        code = cls.EMPTY_CODE
        for attr in _ALPHA_CODES:
            if code := getattr(pc_obj, attr, cls.EMPTY_CODE):
                break
        return code

    @override
    def _deserialize(self: "PyCountryField|Any", value: str, attr: str, *args: "dict[str, None]|dict[str, dict[str, dict[Any, Any]]]|dict[str, dict[str, int]]|dict[str, dict[str, str]]|dict[str, int]|dict[str, list[str]]|dict[str, set[str]]|dict[str, str]|ruamel.yaml.CommentedMap", **kwargs: bool) -> str:
        """Return the alpha 2 encoding."""
        value = super()._deserialize(value, attr, *args, **kwargs)
        code = self.EMPTY_CODE
        if pc_obj := self._get_pycountry(attr, value):
            code = self._to_alpha_code(pc_obj)
        return code

    @override
    def _serialize(self: "PyCountryField|Any", value: str, attr: str, *args: "dict[str, datetime.date|dict[str, dict[Any, Any]]|dict[str, str]|int|list[str]|set[str]|str]", **kwargs: None) -> str:
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
