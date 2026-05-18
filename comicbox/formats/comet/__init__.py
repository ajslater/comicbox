"""
CoMet format package.

http://www.denvog.com/comet/comet-specification/
"""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comet.transform import CoMetTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "CoMet",
        frozenset({"comet"}),
        "CoMet.xml",
        CoMetTransform,
        lexer="xml",
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 4,
            "ARCHIVE_FILE": 5,
            "CLI": 5,
            "API": 6,
        }
    ),
)
