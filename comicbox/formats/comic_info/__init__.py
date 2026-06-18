"""ComicInfo (ComicRack) format package."""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comic_info.transform import ComicInfoTransform
from comicbox.validate.xml_validator import XmlValidator

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "ComicInfo",
        frozenset({"cr", "ci", "cix", "comicinfo", "comicinfoxml", "comicrack"}),
        "ComicInfo.xml",  # CapCase required for the ComicTagger tool to read it
        ComicInfoTransform,
        has_pages=True,
        lexer="xml",
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 2,
            "ARCHIVE_FILE": 4,
            "CLI": 2,
            "API": 4,
        }
    ),
    validator=XmlValidator("ComicInfo-v2.1-Draft.xsd"),
    has_tags_without_ids=True,
)
