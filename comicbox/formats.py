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
