"""json-cbl 1.0: read and write, validated against the vendored spec."""

from comicbox.readinglists.formats import ReadingListFormat
from comicbox.readinglists.formats.json_cbl.transform import JsonCblTransform
from comicbox.validate.spec import ValidatorSpec, ValidatorType

# Vendored byte for byte from github.com/ComicReadingLists/json-cbl-standard,
# schema/1.0/comic-reading-list.schema.json at commit dea268c (2024-09-03).
JSON_CBL_SCHEMA_FILE = "json-cbl-v1.0.schema.json"

JSON_CBL_REGISTRATION = ReadingListFormat(
    label="json-cbl",
    tokens=frozenset({"json-cbl"}),
    suffix=".json",
    transform_class=JsonCblTransform,
    lexer="json",
    validator_spec=ValidatorSpec(ValidatorType.JSON, JSON_CBL_SCHEMA_FILE),
)
