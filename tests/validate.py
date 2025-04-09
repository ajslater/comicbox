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
_CBI_STEMS = tuple(
    variation
    for substring in ("comic-book-info", "comic-book-lover")
    for variation in (substring, substring.replace("-", ""))
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
_NO_VALIDATOR = "no-validator"
_FMT_VALIDATOR_MAP = MappingProxyType(
    {
        "comicinfo": get_xml_schema("ComicInfo-v2.1-Draft.xsd"),
        "comicbookinfo": get_json_schema("comic-book-info-v1.0.schema.json"),
        "metroninfo": get_xml_schema("MetronInfo-v1.0.xsd"),
        "comet": get_xml_schema("CoMet-v1.1.xsd"),
        "json": _CB_SCHEMA,
        "yaml": _CB_SCHEMA,
        "comictagger": _NO_VALIDATOR,
        "pdf": _NO_VALIDATOR,
        "pdfxml": _NO_VALIDATOR,
        "filename": _NO_VALIDATOR,
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


_SUFFIX_SUBSTRINGS = MappingProxyType(
    {
        "json": {
            "comicbox": "json",
            "pdf": "pdf",
            "comictagger": "comictagger",
            **dict.fromkeys(_CBI_STEMS, "comicbookinfo"),
        },
        "xml": {
            "comicinfo": "comicinfo",
            "metron": "metroninfo",
            "comet": "comet",
            "pdf": "pdfxml",
        },
    }
)


def format_guesser(path: Path | str) -> str:
    """Guess format by filename."""
    path = Path(path)
    stem = path.stem.lower()
    suffix = path.suffix[1:].lower()

    fmt = ""
    if suffix in ("xml", "json"):
        fmt_map = _SUFFIX_SUBSTRINGS[suffix]
        for substring, value in fmt_map.items():
            if substring in stem:
                fmt = value
                break
    elif suffix in ("yaml", "yml"):
        fmt = "yaml"
    elif suffix == "txt":
        fmt = "filename"
    else:
        reason = f"Can't guess format for {path} suffix {suffix}"
        raise ValueError(reason)

    if not fmt:
        reason = f"Could not guess format for {path}"
        raise ValueError(reason)
    return fmt


def validate_path(path, fmt=""):
    """Validate a metadata file from disk."""
    path = Path(path)
    if not fmt:
        fmt = format_guesser(path)
    validator = _FMT_VALIDATOR_MAP[fmt]
    if validator == _NO_VALIDATOR:
        # Just pass formats without validators
        return
    if isinstance(validator, str):
        reason = f"validator is {validator}"
        raise TypeError(reason)
    path = Path(path)
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

    argv = sys.argv
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        reason = "no path given"
        raise ValueError(reason)
    fmt = argv[2] if len(argv) > 2 else ""  # noqa: PLR2004
    if not fmt:
        fmt = format_guesser(path)
    print(f"Format {fmt}")
    validate_path(path, fmt)
    print("Valid.")
