"""Xml Validator."""

import sys
from pathlib import Path
from typing import Any

from xmlschema import XMLSchema11

from comicbox.validate.base import BaseValidator

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


class XmlValidator(BaseValidator):
    """Use is_valid on XMLSchema validator."""

    def __init__(self, *args: str, **kwargs: Any) -> None:
        """Set the validator."""
        super().__init__(*args, **kwargs)
        self._validator = XMLSchema11(self.schema_path)

    @override
    def validate(self, data: str | bytes | Path) -> None:
        """Use is_valid on XMLSchema validator."""
        self._validator.validate(data)
