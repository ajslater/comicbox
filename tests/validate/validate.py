"""Validate ComiciInfo.xml test files."""

from pathlib import Path
from types import MappingProxyType

from tests.validate.json_validator import JsonValidator
from tests.validate.xml_validator import XmlValidator
from tests.validate.yaml_validator import YamlValidator

_CBI_STEMS = tuple(
    variation
    for substring in ("comic-book-info", "comic-book-lover")
    for variation in (substring, substring.replace("-", ""))
)
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
_NO_VALIDATOR = "no-validator"
FMT_VALIDATOR_MAP = MappingProxyType(
    {
        "comicinfo": XmlValidator("ComicInfo-v2.1-Draft.xsd"),
        "comicbookinfo": JsonValidator("comic-book-info-v1.0.schema.json"),
        "metroninfo": XmlValidator("MetronInfo-v1.0.xsd"),
        "comet": XmlValidator("CoMet-v1.1.xsd"),
        "json": JsonValidator("v2.0/comicbox-v2.0.schema.json"),
        "yaml": YamlValidator("v2.0/comicbox-v2.0.schema.json"),
        "comictagger": _NO_VALIDATOR,
        "pdf": _NO_VALIDATOR,
        "pdfxml": _NO_VALIDATOR,
        "filename": _NO_VALIDATOR,
    }
)


def guess_format(path: Path | str) -> str:
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
        fmt = guess_format(path)
    validator = FMT_VALIDATOR_MAP[fmt]
    if validator == _NO_VALIDATOR:
        # Just pass formats without validators
        return
    if isinstance(validator, str):
        reason = f"validator is {validator}"
        raise TypeError(reason)
    validator.validate(path)
