"""Validate ComiciInfo.xml test files."""

from pathlib import Path
from types import MappingProxyType

import simplejson
from glom import glom
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from ruamel.yaml import YAML
from xmlschema import XMLSchema11

from comicbox.schemas.comicbox import PAGES_KEY, ComicboxSchemaMixin

PAGES_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{PAGES_KEY}"
_SCHEMAS_PATH = Path("schemas")
_SCHEMA_FS_ROOT = Path(__file__).parent.parent / _SCHEMAS_PATH / "v2.0"
_SCHEMA_ID_ROOT = "https://github.com/ajslater/comicbox/blob/main/schemas/v2.0/"
_DEFAULT_FORMAT_MAP = MappingProxyType(
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


def get_xml_schema(path):
    """Get the xml11 schema."""
    path = _SCHEMAS_PATH / path
    return XMLSchema11(Path(path))


def _retrieve_from_filesystem(uri: str):
    """Resolve local $refs instead of trying the uri for development."""
    # https://python-jsonschema.readthedocs.io/en/latest/referencing/
    relative_path = Path(uri.removeprefix(_SCHEMA_ID_ROOT))
    path = _SCHEMA_FS_ROOT / relative_path
    contents = simplejson.loads(path.read_text())
    return Resource.from_contents(contents)


_REGISTRY = Registry(retrieve=_retrieve_from_filesystem)


def get_json_schema(path):
    """Get the jsonschema."""
    path = _SCHEMAS_PATH / path
    schema_str = path.read_text()
    json_schema = simplejson.loads(schema_str)
    return Draft202012Validator(json_schema, registry=_REGISTRY)


_CB_SCHEMA = get_json_schema("v2.0/comicbox-v2.0.schema.json")
_FMT_SCHEMA_MAP = MappingProxyType(
    {
        "cix": get_xml_schema("ComicInfo-v2.1-Draft.xsd"),
        "cbi": get_json_schema("comic-book-info-v1.0.schema.json"),
        "metron": get_xml_schema("MetronInfo-v1.0.xsd"),
        "comet": get_xml_schema("CoMet-v1.1.xsd"),
        "json": _CB_SCHEMA,
        "yaml": _CB_SCHEMA,
    }
)


def _stringify_keys(data):
    """JSON requires string keys."""
    # Not a general solution. only pages.
    pages = glom(data, PAGES_KEYPATH, default=None)
    if not pages:
        return data
    pages = {str(key): value for key, value in pages.items()}
    # Glom can't assign to RumaelCommentMaps
    data[ComicboxSchemaMixin.ROOT_KEY_PATH][PAGES_KEY] = pages
    return data


def validate_path(path, fmt=None):
    """Validate a metadata file from disk."""
    path = Path(path)
    if fmt is None:
        fmt = _DEFAULT_FORMAT_MAP.get(path.name.lower())
    if not fmt or fmt == "temp-autopass":
        return
    path = Path(path)
    validator = _FMT_SCHEMA_MAP[fmt]
    if isinstance(validator, XMLSchema11):
        validator.validate(path)
        return
    md_string = path.read_text()
    suffix = path.suffix
    if suffix == ".json":
        md_dict = simplejson.loads(md_string)
    elif suffix == ".yaml":
        md_dict = YAML().load(md_string)
        md_dict = _stringify_keys(md_dict)
    else:
        reason = f"Bad suffix for validation: {suffix} : {path}"
        raise ValueError(reason)
    validator.is_valid(md_dict)


if __name__ == "__main__":
    import sys

    validate_path(sys.argv[1], sys.argv[2])
    print("Valid.")
