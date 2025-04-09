"""Xml Validator."""

from pathlib import Path

from xmlschema import XMLSchema11

from tests.validate.base import BaseValidator


class XmlValidator(BaseValidator):
    """Use is_valid on XMLSchema validator."""

    def __init__(self, *args, **kwargs):
        """Set the validator."""
        super().__init__(*args, **kwargs)
        self._validator = XMLSchema11(self.schema_path)

    def is_valid(self, data_path: Path | str):
        """Use is_valid on XMLSchema validator."""
        return self._validator.validate(data_path)
