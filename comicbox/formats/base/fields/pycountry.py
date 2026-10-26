"""Marshmallow pycountry fields."""

import re
from abc import ABC
from typing import Any

import pycountry
from loguru import logger
from pycountry.db import Data, Database
from typing_extensions import override

from comicbox.formats.base.fields.fields import StringField

_ALPHA_CODES = ("alpha_2", "alpha_3", "alpha_4", "name")
# MetronInfo v1.2 languageCode pattern. XSD patterns are implicitly anchored.
_BCP47_RE = re.compile(r"[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*")
_REGION_LEN = 2
_SCRIPT_LEN = 4


class PyCountryField(StringField, ABC):
    """A pycountry value."""

    DB: Database = pycountry.countries
    EMPTY_CODE = ""

    def __init__(
        self,
        *args: Any,
        serialize_name: bool = False,
        allow_empty: bool = False,
        **kwargs: Any,
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
    def _get_pycountry(cls, tag: str, name: str) -> Data | None:
        """Get pycountry object for a country or language tag."""
        try:
            cleaned = cls._clean_name(name)
            if not cleaned:
                return None

            name = cleaned
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
    def _to_alpha_code(cls, pc_obj: Any) -> str:
        code = cls.EMPTY_CODE
        for attr in _ALPHA_CODES:
            if code := getattr(pc_obj, attr, cls.EMPTY_CODE):
                break
        return code

    @classmethod
    def _split(cls, value: str) -> tuple[str, tuple[str, ...]]:
        """Split a value into the part pycountry resolves and a suffix to keep."""
        return value, ()

    @classmethod
    def _resolve(cls, attr: str, value: str, *, name: bool = False) -> str:
        """Resolve the pycountry part to a code or name and re-attach the suffix."""
        primary, suffix = cls._split(value)
        pc_obj = cls._get_pycountry(attr, primary)
        if not pc_obj:
            return cls.EMPTY_CODE
        if name:
            return pc_obj.name
        return "-".join((cls._to_alpha_code(pc_obj), *suffix))

    @override
    def _deserialize(
        self,
        value: str,
        attr: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Return the alpha 2 encoding."""
        value = super()._deserialize(value, attr, *args, **kwargs)
        return self._resolve(attr, value)

    @override
    def _serialize(
        self,
        value: str,
        attr: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Return the long name."""
        serialized = super()._serialize(value, attr, *args, **kwargs)
        if not serialized:
            return self.EMPTY_CODE
        return self._resolve(attr, serialized, name=self._serialize_name)


def _case_subtag(subtag: str) -> str:
    """Case a BCP 47 subtag after the primary language per RFC 5646 §2.1.1."""
    if subtag.isalpha():
        if len(subtag) == _REGION_LEN:
            return subtag.upper()
        if len(subtag) == _SCRIPT_LEN:
            return subtag.title()
    return subtag.lower()


class LanguageField(PyCountryField):
    """
    PyCountry Language Field.

    Holds a BCP 47 tag. Only the primary language subtag is resolved with
    pycountry; script, region and variant subtags are kept as given, recased.
    """

    DB: Database = pycountry.languages

    @override
    @classmethod
    def _split(cls, value: str) -> tuple[str, tuple[str, ...]]:
        """Split a BCP 47 tag into its primary language and recased subtags."""
        value = value.strip()
        if not _BCP47_RE.fullmatch(value):
            # Not a tag: a language name like "English", or garbage pycountry rejects.
            return value, ()
        primary, *subtags = value.split("-")
        suffix: list[str] = []
        singleton = False
        for subtag in subtags:
            # Extension and private use subtags follow a singleton, all lowercase.
            singleton = singleton or len(subtag) == 1
            suffix.append(subtag.lower() if singleton else _case_subtag(subtag))
        return primary, tuple(suffix)


class CountryField(PyCountryField):
    """PyCountry Country Field."""

    DB: Database = pycountry.countries
