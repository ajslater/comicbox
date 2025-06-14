"""Validate yaml with jsonchema."""

from glom import glom
from ruamel.yaml import YAML
from typing_extensions import override

from comicbox.box.pages.covers import PAGES_KEYPATH
from comicbox.schemas.comicbox import PAGES_KEY, ComicboxSchemaMixin
from tests.validate.json_validator import JsonValidator


def _stringify_keys(data):
    """JSON requires string keys."""
    # Not a general solution. only pages.
    pages = glom(data, PAGES_KEYPATH, default=None)
    if not pages:
        return data
    pages = {str(key): value for key, value in pages.items()}
    # Glom can't assign to RumaelCommentMaps
    data[ComicboxSchemaMixin.ROOT_KEYPATH][PAGES_KEY] = pages
    return data


class YamlValidator(JsonValidator):
    """Yaml Validator."""

    @override
    def validate(self, source_path):
        """Validate source."""
        source_str = source_path.read_text()
        data = YAML().load(source_str)
        json_data = _stringify_keys(data)
        self._validator.validate(json_data)
