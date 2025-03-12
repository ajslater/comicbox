"""Metadata sources definitions."""

from dataclasses import dataclass
from enum import Enum

from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox_cli import ComicboxCLITransform
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.pdf import MuPDFTransform, PDFXmlTransform

try:
    from pdffile import PDFFile  # noqa: F401

    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False


@dataclass
class MetadataFormat:
    """Metada format attributes."""

    label: str
    transform_class: type[BaseTransform] = ComicboxJsonTransform
    has_pages: bool = False
    lexer: str = "yaml"
    enabled: bool = True


class MetadataFormats(Enum):
    """Metadata formats."""

    # The order these are listed is the order of masking. Very important.

    FILENAME = MetadataFormat(
        "Filename",
        FilenameTransform,
    )
    COMICTAGGER = MetadataFormat(
        "ComicTagger",
        ComictaggerTransform,
        has_pages=True,
        lexer="json",
    )
    PDF = MetadataFormat(
        "MuPDF",
        MuPDFTransform,
        lexer="json",
        enabled=PDF_ENABLED,
    )
    PDF_XML = MetadataFormat(
        "PDF XML",
        PDFXmlTransform,
        lexer="xml",
        enabled=PDF_ENABLED,
    )
    COMET = MetadataFormat(
        "CoMet",
        CoMetTransform,
        lexer="xml",
    )
    CBI = MetadataFormat(
        "ComicBookInfo",
        ComicBookInfoTransform,
        lexer="json",
    )
    CIX = MetadataFormat(
        "ComicInfo",
        ComicInfoTransform,
        has_pages=True,
        lexer="xml",
    )
    METRON = MetadataFormat(
        "MetronInfo",
        MetronInfoTransform,
        has_pages=True,
        lexer="xml",
    )
    COMICBOX_YAML = MetadataFormat(
        "Comicbox YAML",
        ComicboxYamlTransform,
        has_pages=True,
    )
    COMICBOX_JSON = MetadataFormat(
        "Comicbox JSON",
        ComicboxJsonTransform,
        has_pages=True,
        lexer="json",
    )
    COMICBOX_CLI_YAML = MetadataFormat(
        "Comicbox CLI Yaml", ComicboxCLITransform, has_pages=True, lexer="yaml"
    )


@dataclass
class MetadataSource:
    """Metadata source attributes."""

    label: str
    path: bool = False
    formats: tuple[MetadataFormats, ...] = tuple(
        fmt for fmt in MetadataFormats if fmt.value.enabled
    )
    from_archive: bool = False


class MetadataSources(Enum):
    """Metadata sources."""

    # Source order declares masking precedence
    # Format tuples declare masking precedence under each source

    CONFIG = MetadataSource(
        "Config",
        formats=(
            MetadataFormats.COMICBOX_YAML,
            MetadataFormats.METRON,
            MetadataFormats.CIX,
            MetadataFormats.CBI,
            MetadataFormats.COMET,
            MetadataFormats.PDF,
            MetadataFormats.COMICTAGGER,
            MetadataFormats.FILENAME,
        ),
    )
    ARCHIVE_FILENAME = MetadataSource(
        "Filename", path=True, formats=(MetadataFormats.FILENAME,), from_archive=True
    )
    ARCHIVE_PDF = MetadataSource(
        "Archive Header", path=True, formats=(MetadataFormats.PDF,), from_archive=True
    )
    ARCHIVE_COMMENT = MetadataSource(
        "Archive Comment", path=True, formats=(MetadataFormats.CBI,), from_archive=True
    )
    ARCHIVE_FILE = MetadataSource(
        "Archive File",
        path=True,
        formats=(
            MetadataFormats.COMICBOX_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON,
            MetadataFormats.CIX,
            MetadataFormats.COMET,
            MetadataFormats.CBI,
            MetadataFormats.COMICTAGGER,
        ),
        from_archive=True,
    )
    ARCHIVE_EMBEDDED = MetadataSource(
        "Embedded in Other Metadata",
        path=True,
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.METRON,
            MetadataFormats.CIX,
            MetadataFormats.FILENAME,
        ),
        from_archive=True,
    )
    IMPORT_FILE = MetadataSource("Imported File", path=True)
    CLI = MetadataSource(
        "Comicbox CLI",
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON,
            MetadataFormats.CIX,
            MetadataFormats.CBI,
            MetadataFormats.PDF,
            MetadataFormats.COMET,
            MetadataFormats.COMICTAGGER,
        ),
    )
    API = MetadataSource(
        "API",
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.COMICBOX_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.METRON,
            MetadataFormats.CIX,
            MetadataFormats.CBI,
            MetadataFormats.COMET,
            MetadataFormats.PDF,
            MetadataFormats.PDF_XML,
            MetadataFormats.COMICTAGGER,
            MetadataFormats.FILENAME,
        ),
    )
