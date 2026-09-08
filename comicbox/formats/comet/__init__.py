"""
CoMet format package.

http://www.denvog.com/comet/comet-specification/
"""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comet.transform import CoMetTransform
from comicbox.validate.spec import ValidatorSpec, ValidatorType

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
    validator_spec=ValidatorSpec(ValidatorType.XML, "CoMet-v1.1.xsd"),
)
