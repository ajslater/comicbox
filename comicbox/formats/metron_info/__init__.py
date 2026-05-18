"""MetronInfo (Metron) format package."""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.metron_info.transform import MetronInfoTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "MetronInfo",
        frozenset({"metron", "metroninfo", "mi", "mix"}),
        "MetronInfo.xml",
        MetronInfoTransform,
        has_pages=True,
        lexer="xml",
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 1,
            "ARCHIVE_FILE": 3,
            "CLI": 1,
            "API": 3,
        }
    ),
)
