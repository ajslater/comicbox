"""Metadata sources definitions."""
from dataclasses import dataclass
from enum import Enum

from comicbox.schemas.cli import CLISchema
from comicbox.schemas.comet import CoMetSchema
from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox_base import ComicboxBaseSchema
from comicbox.schemas.comicinfo import ComicInfoSchema
from comicbox.schemas.comictagger import ComictaggerSchema
from comicbox.schemas.filename import FilenameSchema
from comicbox.schemas.json import ComicboxJsonSchema
from comicbox.schemas.pdf import PDFSchema
from comicbox.schemas.yaml import ComicboxYamlSchema


class SourceFrom(Enum):
    """How to get the source."""

    OTHER = 0
    ARCHIVE_FILENAME = 1
    ARCHIVE_CONTENTS = 2
    ARCHIVE_COMMENT = 3
    ARCHIVE_FILE = 4


@dataclass
class MetadataSource:
    """Metadata source attributes."""

    label: str
    schema_class: type[ComicboxBaseSchema] = ComicboxJsonSchema
    configurable: bool = False
    from_archive: SourceFrom = SourceFrom.OTHER
    writable: bool = False


class MetadataSources(Enum):
    """Metadata sources."""

    # If adding a file source be sure to update CLISchema.loads()
    # The order these are listed is the order of masking. Very important.

    CONFIG = MetadataSource("Config")
    FILENAME = MetadataSource(
        "Filename",
        FilenameSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILENAME,
    )
    PDF = MetadataSource(
        "PDF",
        PDFSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_CONTENTS,
        writable=True,
    )
    COMET = MetadataSource(
        "CoMet",
        CoMetSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
    )
    CBI = MetadataSource(
        "ComicBookInfo",
        ComicBookInfoSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_COMMENT,
        writable=True,
    )
    CIX = MetadataSource(
        "ComicInfo",
        ComicInfoSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
    )
    COMICTAGGER = MetadataSource(
        "ComicTagger",
        ComictaggerSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
    )
    COMICBOX_YAML = MetadataSource(
        "Comicbox YAML",
        ComicboxYamlSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
    )
    COMICBOX_JSON = MetadataSource(
        "Comicbox JSON",
        ComicboxJsonSchema,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
    )
    IMPORT = MetadataSource("Imported File")
    CLI = MetadataSource("Comicbox CLI", CLISchema, configurable=True, writable=True)
    API = MetadataSource("API")
    ADDED = MetadataSource(
        "API Added",
    )
