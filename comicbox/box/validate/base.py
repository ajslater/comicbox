"""Base validator."""

from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema_definitions"


class BaseValidator:
    """Base validator."""

    def __init__(self, schema_path: Path | str):
        """Set the full schema path."""
        self.schema_path = SCHEMA_PATH / schema_path

    @staticmethod
    def get_data_str(data: str | bytes | Path) -> str:
        """Get data string from bytes or a path."""
        if isinstance(data, bytes):
            data = data.decode()
        elif isinstance(data, Path):
            data = data.read_text()
        return data
