"""Metadata sources definitions."""

from dataclasses import dataclass
from enum import Enum

from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_cli import (
    ComicboxCLITransform,
)
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.pdf import MuPDFTransform, PDFXmlTransform


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
    transform_class: type[BaseTransform] = ComicboxJsonTransform
    configurable: bool = False
    from_archive: SourceFrom = SourceFrom.OTHER
    writable: bool = False
    has_page_count: bool = False
    has_pages: bool = False


class MetadataSources(Enum):
    """Metadata sources."""

    # If adding a file source be sure to update CLITransform.loads()
    # The order these are listed is the order of masking. Very important.

    CONFIG = MetadataSource("Config")
    FILENAME = MetadataSource(
        "Filename",
        FilenameTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILENAME,
    )
    COMICTAGGER = MetadataSource(
        "ComicTagger",
        ComictaggerTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
        has_pages=True,
    )
    PDF = MetadataSource(
        "MuPDF",
        MuPDFTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_CONTENTS,
        writable=True,
        has_page_count=True,
    )
    PDF_XML = MetadataSource(
        "PDF XML",
        PDFXmlTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
    )
    COMET = MetadataSource(
        "CoMet",
        CoMetTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
    )
    METRON = MetadataSource(
        "MetronInfo",
        MetronInfoTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
        has_pages=True,
    )
    CBI = MetadataSource(
        "ComicBookInfo",
        ComicBookInfoTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_COMMENT,
        writable=True,
        has_page_count=True,
    )
    CIX = MetadataSource(
        "ComicInfo",
        ComicInfoTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
        has_pages=True,
    )
    COMICBOX_YAML = MetadataSource(
        "Comicbox YAML",
        ComicboxYamlTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
        has_pages=True,
    )
    COMICBOX_JSON = MetadataSource(
        "Comicbox JSON",
        ComicboxJsonTransform,
        configurable=True,
        from_archive=SourceFrom.ARCHIVE_FILE,
        writable=True,
        has_page_count=True,
        has_pages=True,
    )
    IMPORT = MetadataSource("Imported File")
    CLI = MetadataSource(
        "Comicbox CLI",
        ComicboxCLITransform,
        configurable=True,
        writable=True,
    )
    API = MetadataSource("API")
    ADDED = MetadataSource(
        "API Added",
    )
