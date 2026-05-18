"""Validate yaml with jsonchema."""

from pathlib import Path
from typing import Any

from glom import glom
from ruamel.yaml import YAML
from typing_extensions import override

from comicbox.box.validate.json_validator import JsonValidator
from comicbox.constants import (
    COVER_DATE_KEY,
    COVER_DATE_KEYPATH,
    DATE_KEY,
    PAGES_KEY,
    PAGES_KEYPATH,
    ROOT_KEYPATH,
    STORE_DATE_KEY,
    STORE_DATE_KEYPATH,
    UPDATED_AT_KEY,
)
from comicbox.formats.base.fields.time_fields import DateField, DateTimeField

_KEYPATH_PREFIX = ROOT_KEYPATH + "."
_FULL_UPDATED_AT_KEYPATH = _KEYPATH_PREFIX + UPDATED_AT_KEY
_FULL_COVER_DATE_KEYPATH = _KEYPATH_PREFIX + COVER_DATE_KEYPATH
_FULL_STORE_DATE_KEYPATH = _KEYPATH_PREFIX + STORE_DATE_KEYPATH


def _stringify_keys(data: Any) -> Any:
    """JSON requires string keys."""
    if pages := glom(data, PAGES_KEYPATH, default=None):
        pages = {str(key): value for key, value in pages.items()}
        # Glom can't assign to RumaelCommentMaps
        data[ROOT_KEYPATH][PAGES_KEY] = pages

    if updated_at := glom(data, _FULL_UPDATED_AT_KEYPATH, default=None):
        data[ROOT_KEYPATH][UPDATED_AT_KEY] = updated_at = DateTimeField()._serialize(  # noqa: SLF001
            updated_at, "", None
        )

    if cover_date := glom(data, _FULL_COVER_DATE_KEYPATH, default=None):
        data[ROOT_KEYPATH][DATE_KEY][COVER_DATE_KEY] = DateField()._serialize(  # noqa: SLF001
            cover_date, "", None
        )

    if store_date := glom(data, _FULL_STORE_DATE_KEYPATH, default=None):
        data[ROOT_KEYPATH][DATE_KEY][STORE_DATE_KEY] = DateField()._serialize(  # noqa: SLF001
            store_date, "", None
        )

    return data


class YamlValidator(JsonValidator):
    """Yaml Validator."""

    @override
    def validate(self, data: str | bytes | Path) -> None:
        """Validate source."""
        data = self.get_data_str(data)
        data = YAML().load(data)
        json_data = _stringify_keys(data)
        self._validator.validate(json_data)
