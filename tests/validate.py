"""Validate ComiciInfo.xml test files."""

from pathlib import Path
from types import MappingProxyType

import simplejson
from jsonschema import validate as jsonschema_validate
from ruamel.yaml import YAML
from xmlschema import XMLSchema11

TEST_FILES_PATH = Path("tests/test_files")
# TODO replace this with a validator for each written file in regular tests.


def get_xml_schema(path):
    """Get the xml11 schema."""
    return XMLSchema11(Path(path))


def get_json_schema(path):
    """Get the jsonschema."""
    with Path(path).open("r") as f:
        schema_str = f.read()
    return simplejson.loads(schema_str)


CBI_SCHEMA = get_json_schema("schemas/comic-book-info-v1.0.schema.json")
CB_SCHEMA = get_json_schema("schemas/comicbox-v2.0.schema.json")
MIX_SCHEMA = get_xml_schema("schemas/MetronInfo-v1.0.xsd")
CIX_SCHEMA = get_xml_schema("schemas/ComicInfo-v2.1-Draft.xsd")
COMET_SCHEMA = get_xml_schema("schemas/CoMet-v1.1.xsd")

FMT_SCHEMA_MAP = MappingProxyType(
    {
        "cix": CIX_SCHEMA,
        "cbi": CBI_SCHEMA,
        "metron": MIX_SCHEMA,
        "comet": COMET_SCHEMA,
        "json": CB_SCHEMA,
        "yaml": CB_SCHEMA,
    }
)

DEFAULT_FORMAT_MAP = MappingProxyType(
    {
        # "comicbox.json": "json",
        # "comicbox.yaml": "yaml",
        # "comicbox-cli.yaml": "yaml"
        "comicinfo.xml": "cix",
        "comic-book-info.json": "cbi",
        "metroninfo.xml": "metron",
        "comet.xml": "comet",
        "comictagger.json": "no-validation",
        "mupdf.json": "no-validation",
        "comicbox.json": "temp-autopass",
        "comicbox.yaml": "temp-autopass",
        "comicbox-cli.yaml": "temp-autopass",
    }
)


def validate_path(path, fmt=None):
    """Validate a metadata file from disk."""
    if fmt is None:
        fmt = DEFAULT_FORMAT_MAP[path.name.lower()]
    if fmt == "temp-autopass":
        return
    if fmt == "no-validation":
        return
    path = Path(path)
    schema = FMT_SCHEMA_MAP[fmt]
    suffix = path.suffix
    if suffix == ".xml":
        xml_schema: XMLSchema11 = schema  # type: ignore[reportAssignmentType]
        xml_schema.validate(path)
    else:
        print(path)
        with Path(path).open("r") as f:
            md_string = f.read()
        if suffix == ".json":
            md_dict = simplejson.loads(md_string)
        elif suffix == ".yaml":
            md_dict = YAML().load(md_string)
        else:
            reason = f"Bad suffix for validation: {suffix} : {path}"
            raise ValueError(reason)
        json_schema: dict = schema  # type: ignore[reportAssignmentType]
        jsonschema_validate(instance=md_dict, schema=json_schema)
