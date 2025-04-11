"""Custom jsonschema validator."""

from pathlib import Path

import simplejson
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from tests.const import SCHEMAS_DIR
from tests.validate.base import BaseValidator

_SCHEMA_FS_ROOT = SCHEMAS_DIR / "v2.0"
_SCHEMA_ID_ROOT = "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/"


def _retrieve_from_filesystem(uri: str):
    """Resolve local $refs instead of trying the uri for development."""
    # https://python-jsonschema.readthedocs.io/en/latest/referencing/
    relative_path = Path(uri.removeprefix(_SCHEMA_ID_ROOT))
    path = _SCHEMA_FS_ROOT / relative_path
    contents = simplejson.loads(path.read_text())
    return Resource.from_contents(contents)


_FILESYSTEM_RESOLVING_REGISTRY = Registry(retrieve=_retrieve_from_filesystem)


class JsonValidator(BaseValidator):
    """Validate json with jsonchema validator."""

    def __init__(self, *args, **kwargs):
        """Create jsonchema validator."""
        super().__init__(*args, **kwargs)
        schema_str = self.schema_path.read_text()
        schema = simplejson.loads(schema_str)
        self._validator = Draft202012Validator(
            schema,
            registry=_FILESYSTEM_RESOLVING_REGISTRY,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

    def validate(self, source_path: Path):
        """Validate source."""
        source_str = source_path.read_text()
        data = simplejson.loads(source_str)
        self._validator.validate(data)
