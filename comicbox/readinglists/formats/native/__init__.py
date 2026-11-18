"""
Comicbox's own reading-list serializations, YAML and JSON.

Both carry the model whole, so their transforms are the identity.
"""

from comicbox.readinglists.formats import ReadingListFormat
from comicbox.readinglists.formats.native.transform import (
    ReadingListJsonTransform,
    ReadingListYamlTransform,
)
from comicbox.validate.spec import ValidatorSpec, ValidatorType

_READING_LIST_SCHEMA_FILE = "reading-list/v1.0/reading-list-v1.0.schema.json"

YAML_REGISTRATION = ReadingListFormat(
    label="Comicbox Reading List YAML",
    tokens=frozenset({"yaml", "comicbox-yaml"}),
    suffix=".yaml",
    transform_class=ReadingListYamlTransform,
    lexer="yaml",
    validator_spec=ValidatorSpec(ValidatorType.YAML, _READING_LIST_SCHEMA_FILE),
)

JSON_REGISTRATION = ReadingListFormat(
    label="Comicbox Reading List JSON",
    tokens=frozenset({"json", "comicbox-json"}),
    suffix=".json",
    transform_class=ReadingListJsonTransform,
    lexer="json",
    validator_spec=ValidatorSpec(ValidatorType.JSON, _READING_LIST_SCHEMA_FILE),
)
