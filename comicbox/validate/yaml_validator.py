"""Validate yaml with jsonchema."""

import sys
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from comicbox.formats.base.fields.time_fields import DateField, DateTimeField
from comicbox.validate.json_validator import JsonValidator

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


def _jsonable(data: Any) -> Any:
    """
    Make loaded YAML look like the JSON the schema describes.

    JSON keys are strings, and JSON has no date type: YAML loads page
    numbers as int keys and dates as date objects, wherever they sit, in a
    comic's cover date or in every entry of a reading list.
    """
    if isinstance(data, Mapping):
        return {str(key): _jsonable(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_jsonable(value) for value in data]
    if isinstance(data, datetime):
        return DateTimeField()._serialize(data, "", None)  # noqa: SLF001
    if isinstance(data, date):
        return DateField()._serialize(data, "", None)  # noqa: SLF001
    return data


class YamlValidator(JsonValidator):
    """Yaml Validator."""

    @override
    def validate(self, data: str | bytes | Path) -> None:
        """Validate source."""
        data = self.get_data_str(data)
        data = YAML().load(data)
        self._validator.validate(_jsonable(data))
