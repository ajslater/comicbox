"""Validate yaml with jsonchema."""

from glom import glom
from ruamel.yaml import YAML
from typing_extensions import override

from comicbox.box.pages.covers import PAGES_KEYPATH
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.schemas.comicbox import (
    COVER_DATE_KEY,
    DATE_KEY,
    PAGES_KEY,
    STORE_DATE_KEY,
    UPDATED_AT_KEY,
    ComicboxSchemaMixin,
)
from comicbox.transforms.comicbox import (
    COVER_DATE_KEYPATH,
    STORE_DATE_KEYPATH,
)
from tests.validate.json_validator import JsonValidator

_KEYPATH_PREFIX = ComicboxSchemaMixin.ROOT_KEYPATH + "."

FULL_UPDATED_AT_KEYPATH = _KEYPATH_PREFIX + UPDATED_AT_KEY
FULL_COVER_DATE_KEYPATH = _KEYPATH_PREFIX + COVER_DATE_KEYPATH
FULL_STORE_DATE_KEYPATH = _KEYPATH_PREFIX + STORE_DATE_KEYPATH


def _stringify_keys(data):
    """JSON requires string keys."""
    if pages := glom(data, PAGES_KEYPATH, default=None):
        pages = {str(key): value for key, value in pages.items()}
        # Glom can't assign to RumaelCommentMaps
        data[ComicboxSchemaMixin.ROOT_KEYPATH][PAGES_KEY] = pages

    if updated_at := glom(data, FULL_UPDATED_AT_KEYPATH, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][UPDATED_AT_KEY] = updated_at = (
            DateTimeField()._serialize(updated_at, "", None)  # noqa: SLF001
        )

    if cover_date := glom(data, FULL_COVER_DATE_KEYPATH, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][DATE_KEY][COVER_DATE_KEY] = (
            DateField()._serialize(cover_date, "", None)  # noqa: SLF001
        )

    if store_date := glom(data, FULL_STORE_DATE_KEYPATH, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][DATE_KEY][STORE_DATE_KEY] = (
            DateField()._serialize(store_date, "", None)  # noqa: SLF001
        )

    return data


class YamlValidator(JsonValidator):
    """Yaml Validator."""

    @override
    def validate(self, source_path):
        """Validate source."""
        source_str = source_path.read_text()
        data = YAML().load(source_str)
        json_data = _stringify_keys(data)
        self._validator.validate(json_data)
