"""Filename format package."""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.filename.transform import FilenameTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "Filename",
        frozenset({"fn", "filename"}),
        "comicbox-filename.txt",
        FilenameTransform,
        lexer="",
    ),
    sources=MappingProxyType(
        {
            "ARCHIVE_FILENAME": 0,
            "CONFIG": 6,
            "API": 9,
        }
    ),
)
