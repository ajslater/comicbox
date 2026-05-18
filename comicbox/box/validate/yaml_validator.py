"""Validate yaml with jsonchema."""

from pathlib import Path
from typing import Any

from glom import glom
from ruamel.yaml import YAML
from typing_extensions import override

from comicbox.box.validate.json_validator import JsonValidator
from comicbox.fields.time_fields import DateField, DateTimeField


def _stringify_keys(data: Any) -> Any:
    """JSON requires string keys."""
    # Deferred imports: the comicbox-native format module's REGISTRATION
    # references YamlValidator, so top-level imports here would re-enter
    # the formats package (and box.pages, which transitively depends on
    # formats) during its own initialisation.
    from comicbox.box.pages.covers import PAGES_KEYPATH
    from comicbox.formats.comicbox.schema import (
        COVER_DATE_KEY,
        DATE_KEY,
        PAGES_KEY,
        STORE_DATE_KEY,
        UPDATED_AT_KEY,
        ComicboxSchemaMixin,
    )
    from comicbox.formats.comicbox.transform import (
        COVER_DATE_KEYPATH,
        STORE_DATE_KEYPATH,
    )

    _keypath_prefix = ComicboxSchemaMixin.ROOT_KEYPATH + "."
    full_updated_at_keypath = _keypath_prefix + UPDATED_AT_KEY
    full_cover_date_keypath = _keypath_prefix + COVER_DATE_KEYPATH
    full_store_date_keypath = _keypath_prefix + STORE_DATE_KEYPATH

    if pages := glom(data, PAGES_KEYPATH, default=None):
        pages = {str(key): value for key, value in pages.items()}
        # Glom can't assign to RumaelCommentMaps
        data[ComicboxSchemaMixin.ROOT_KEYPATH][PAGES_KEY] = pages

    if updated_at := glom(data, full_updated_at_keypath, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][UPDATED_AT_KEY] = updated_at = (
            DateTimeField()._serialize(updated_at, "", None)  # noqa: SLF001
        )

    if cover_date := glom(data, full_cover_date_keypath, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][DATE_KEY][COVER_DATE_KEY] = (
            DateField()._serialize(cover_date, "", None)  # noqa: SLF001
        )

    if store_date := glom(data, full_store_date_keypath, default=None):
        data[ComicboxSchemaMixin.ROOT_KEYPATH][DATE_KEY][STORE_DATE_KEY] = (
            DateField()._serialize(store_date, "", None)  # noqa: SLF001
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
