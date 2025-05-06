"""Metadata sources definitions."""

from dataclasses import dataclass
from enum import Enum

from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet import CoMetTransform
from comicbox.transforms.comicbookinfo import ComicBookInfoTransform
from comicbox.transforms.comicbox.cli import ComicboxCLITransform
from comicbox.transforms.comicbox.json import ComicboxJsonTransform
from comicbox.transforms.comicbox.yaml import ComicboxYamlTransform
from comicbox.transforms.comicinfo import ComicInfoTransform
from comicbox.transforms.comictagger import ComictaggerTransform
from comicbox.transforms.filename import FilenameTransform
from comicbox.transforms.metroninfo import MetronInfoTransform
from comicbox.transforms.pdf import MuPDFTransform, PDFXmlTransform


def _get_pdf_enabled():
    try:
        from pdffile import PDFFile  # pyright: ignore[reportUnusedImport]

        result = True
    except ImportError:
        from comicbox.box.pdffile_stub import (
            PDFFile,  # noqa: F401 # pyright: ignore[reportUnusedImport]
        )

        result = False
    return result


PDF_ENABLED = _get_pdf_enabled()


@dataclass
class MetadataFormat:
    """Metada format attributes."""

    label: str
    config_keys: frozenset
    filename: str
    transform_class: type[BaseTransform]
    has_pages: bool = False
    lexer: str = "yaml"
    enabled: bool = True

    def __post_init__(self):
        """Hoist the schema class."""
        self.schema_class = self.transform_class.SCHEMA_CLASS  # pyright: ignore[reportUninitializedInstanceVariable]


class MetadataFormats(Enum):
    """Metadata formats."""

    # The order these are listed is the order of masking. Very important.

    FILENAME = MetadataFormat(
        "Filename",
        frozenset({"fn", "filename"}),
        "comicbox-filename.txt",
        FilenameTransform,
        lexer="",
    )
    COMICTAGGER = MetadataFormat(
        "ComicTagger",
        frozenset({"comictagger", "ct"}),
        "comictagger.json",
        ComictaggerTransform,
        has_pages=True,
        lexer="json",
    )
    PDF = MetadataFormat(
        "MuPDF",
        frozenset({"pdf", "mudpdf"}),
        "mupdf.json",
        MuPDFTransform,
        lexer="json",
        enabled=PDF_ENABLED,
    )
    PDF_XML = MetadataFormat(
        "PDF XML",
        frozenset({"pdfxml"}),
        "pdf.xml",
        PDFXmlTransform,
        lexer="xml",
        enabled=PDF_ENABLED,
    )
    COMET = MetadataFormat(
        "CoMet",
        frozenset({"comet"}),
        "CoMet.xml",
        CoMetTransform,
        lexer="xml",
    )
    COMIC_BOOK_INFO = MetadataFormat(
        "ComicBookInfo",
        frozenset({"cbi", "cbl", "comicbookinfo", "comicbooklover"}),
        "comic-book-info.json",
        ComicBookInfoTransform,
        lexer="json",
    )
    COMIC_INFO = MetadataFormat(
        "ComicInfo",
        frozenset({"cr", "ci", "cix", "comicinfo", "comicinfoxml", "comicrack"}),
        "ComicInfo.xml",  # Comictagger doesn't read without CapCase
        ComicInfoTransform,
        has_pages=True,
        lexer="xml",
    )
    METRON_INFO = MetadataFormat(
        "MetronInfo",
        frozenset({"metron", "metroninfo", "mi", "mix"}),
        "MetronInfo.xml",
        MetronInfoTransform,
        has_pages=True,
        lexer="xml",
    )
    COMICBOX_YAML = MetadataFormat(
        "Comicbox YAML",
        frozenset({"comicbox-yaml", "yaml"}),
        "comicbox.yaml",
        ComicboxYamlTransform,
        has_pages=True,
    )
    COMICBOX_JSON = MetadataFormat(
        "Comicbox JSON",
        frozenset({"cb", "comicbox", "json", "comicbox-json"}),
        "comicbox.json",
        ComicboxJsonTransform,
        has_pages=True,
        lexer="json",
    )
    COMICBOX_CLI_YAML = MetadataFormat(
        "Comicbox CLI Yaml",
        frozenset({"cli", "comicbox-cli", "embedded"}),
        "comicbox-cli.yaml",
        ComicboxCLITransform,
        has_pages=True,
        lexer="yaml",
    )
