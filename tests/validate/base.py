"""Base validator."""

from pathlib import Path

from tests.const import SCHEMAS_DIR


class BaseValidator:
    """Base validator."""

    def __init__(self, schema_path: Path | str):
        """Set the full schema path."""
        self.schema_path = SCHEMAS_DIR / schema_path
