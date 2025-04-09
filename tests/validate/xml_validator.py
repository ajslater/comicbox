"""Xml Validator."""

from pathlib import Path

from xmlschema import XMLSchema11

from tests.const import SCHEMAS_DIR


class XmlValidator:
    """Use is_valid on XMLSchema validator."""

    def __init__(self, schema_path: Path | str):
        """Set the validator."""
        full_schema_path = SCHEMAS_DIR / schema_path
        self._validator = XMLSchema11(full_schema_path)

    def is_valid(self, data_path: Path | str):
        """Use is_valid on XMLSchema validator."""
        return self._validator.validate(data_path)
