"""Custom jsonschema validator."""

from pathlib import Path

import simplejson
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource

from comicbox.box.validate.base import SCHEMA_PATH, BaseValidator

_SCHEMA_ID_ROOT = "https://github.com/ajslater/comicbox/blob/main/schemas/"


def _retrieve_from_filesystem(uri: str):
    """Resolve local $refs instead of trying the uri for development."""
    # https://python-jsonschema.readthedocs.io/en/latest/referencing/
    relative_path = Path(uri.removeprefix(_SCHEMA_ID_ROOT))
    path = SCHEMA_PATH / relative_path
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

    def validate(self, data: str | bytes | Path):
        """Validate source."""
        data = self.get_data_str(data)
        data = simplejson.loads(data)
        self._validator.validate(data)
