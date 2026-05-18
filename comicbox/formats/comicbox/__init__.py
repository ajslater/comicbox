"""
Comicbox-native format package (YAML, JSON, CLI YAML serializations).

Three REGISTRATIONs share schema + transform helpers in this package:
- YAML_REGISTRATION (`comicbox.yaml`)
- JSON_REGISTRATION (`comicbox.json`)
- CLI_YAML_REGISTRATION (`comicbox-cli.yaml`)
"""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comicbox.transform.cli import ComicboxCLITransform
from comicbox.formats.comicbox.transform.json import ComicboxJsonTransform
from comicbox.formats.comicbox.transform.yaml import ComicboxYamlTransform

YAML_REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "Comicbox YAML",
        frozenset({"comicbox-yaml", "yaml"}),
        "comicbox.yaml",
        ComicboxYamlTransform,
        has_pages=True,
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 0,
            "ARCHIVE_FILE": 0,
            "API": 1,
        }
    ),
)

JSON_REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "Comicbox JSON",
        frozenset({"cb", "comicbox", "json", "comicbox-json"}),
        "comicbox.json",
        ComicboxJsonTransform,
        has_pages=True,
        lexer="json",
    ),
    sources=MappingProxyType(
        {
            "ARCHIVE_FILE": 1,
            "API": 2,
        }
    ),
)

CLI_YAML_REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "Comicbox CLI Yaml",
        frozenset({"cli", "comicbox-cli"}),
        "comicbox-cli.yaml",
        ComicboxCLITransform,
        has_pages=True,
        lexer="yaml",
    ),
    sources=MappingProxyType(
        {
            "ARCHIVE_FILE": 2,
            "CLI": 0,
            "API": 0,
        }
    ),
)
