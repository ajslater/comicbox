"""Xml Validator."""

from pathlib import Path

from xmlschema import XMLSchema11

from comicbox.box.validate.base import BaseValidator


class XmlValidator(BaseValidator):
    """Use is_valid on XMLSchema validator."""

    def __init__(self, *args, **kwargs):
        """Set the validator."""
        super().__init__(*args, **kwargs)
        self._validator = XMLSchema11(self.schema_path)

    def validate(self, data: str | bytes | Path):
        """Use is_valid on XMLSchema validator."""
        self._validator.validate(data)
