"""Validate ComiciInfo.xml test files."""

from pathlib import Path
from types import MappingProxyType

import simplejson
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from ruamel.yaml import YAML
from xmlschema import XMLSchema11

SCHEMAS_PATH = Path("schemas")


def get_xml_schema(path):
    """Get the xml11 schema."""
    path = SCHEMAS_PATH / path
    return XMLSchema11(Path(path))


SCHEMA_ROOT = Path(__file__).parent.parent / "schemas/v2.0"
SCHEMA_ID = "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/"


def _retrieve_from_filesystem(uri: str):
    """Resolve local $refs instead of trying the uri for development."""
    # https://python-jsonschema.readthedocs.io/en/latest/referencing/
    path = SCHEMA_ROOT / Path(uri.removeprefix(SCHEMA_ID))
    contents = simplejson.loads(path.read_text())
    return Resource.from_contents(contents)


REGISTRY = Registry(retrieve=_retrieve_from_filesystem)


def get_json_schema(path):
    """Get the jsonschema."""
    path = SCHEMAS_PATH / path
    with Path(path).open("r") as f:
        schema_str = f.read()
    json_schema = simplejson.loads(schema_str)
    return Draft202012Validator(json_schema, registry=REGISTRY)


CB_SCHEMA = get_json_schema("v2.0/comicbox-v2.0.schema.json")
FMT_SCHEMA_MAP = MappingProxyType(
    {
        "cix": get_xml_schema("ComicInfo-v2.1-Draft.xsd"),
        "cbi": get_json_schema("comic-book-info-v1.0.schema.json"),
        "metron": get_xml_schema("MetronInfo-v1.0.xsd"),
        "comet": get_xml_schema("CoMet-v1.1.xsd"),
        "json": CB_SCHEMA,
        "yaml": CB_SCHEMA,
    }
)
DEFAULT_FORMAT_MAP = MappingProxyType(
    {
        "comicbox.json": "json",
        "comicbox.yaml": "yaml",
        "comicbox-cli.yaml": "yaml",
        "comicinfo.xml": "cix",
        "comic-book-info.json": "cbi",
        "metroninfo.xml": "metron",
        "comet.xml": "comet",
        # "comictagger.json": "no-validation",
        # "mupdf.json": "no-validation",
        # "pdf-metadata.xml": "no-validation",
    }
)


def validate_path(path, fmt=None):
    """Validate a metadata file from disk."""
    if fmt is None:
        fmt = DEFAULT_FORMAT_MAP.get(path.name.lower())
    if not fmt or fmt == "temp-autopass":
        return
    path = Path(path)
    validator = FMT_SCHEMA_MAP[fmt]
    suffix = path.suffix
    if isinstance(validator, XMLSchema11):
        validator.validate(path)
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
        validator.is_valid(md_dict)
