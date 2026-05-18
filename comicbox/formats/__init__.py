"""
Metadata formats registry.

`MetadataFormats` is assembled from per-format packages (under
`comicbox.formats.<name>`) plus inline declarations for formats not
yet migrated to the format-package layout. Each migrated format
exports a `REGISTRATION: FormatRegistration` from its `__init__.py`.
"""

from enum import Enum

from comicbox._pdf import PDF_ENABLED
from comicbox.formats._base import MetadataFormat
from comicbox.formats.comet import REGISTRATION as _COMET_REGISTRATION
from comicbox.formats.comic_book_info import (
    REGISTRATION as _COMIC_BOOK_INFO_REGISTRATION,
)
from comicbox.formats.comic_info import REGISTRATION as _COMIC_INFO_REGISTRATION
from comicbox.formats.filename import REGISTRATION as _FILENAME_REGISTRATION
from comicbox.formats.metron_info import REGISTRATION as _METRON_INFO_REGISTRATION
from comicbox.transforms.comicbox.cli import ComicboxCLITransform
from comicbox.transforms.comicbox.json import ComicboxJsonTransform
from comicbox.transforms.comicbox.yaml import ComicboxYamlTransform
from comicbox.transforms.comicvine_api import ComicVineApiTransform
from comicbox.transforms.metron_api import MetronApiTransform
from comicbox.transforms.pdf import MuPDFTransform, PDFXmlTransform


class MetadataFormats(Enum):
    """Metadata formats."""

    # The order these are listed is the order of masking. Very important.

    FILENAME = _FILENAME_REGISTRATION.format
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
    COMET = _COMET_REGISTRATION.format
    COMIC_BOOK_INFO = _COMIC_BOOK_INFO_REGISTRATION.format
    COMIC_INFO = _COMIC_INFO_REGISTRATION.format
    METRON_INFO = _METRON_INFO_REGISTRATION.format
    METRON_API = MetadataFormat(
        "Metron API",
        frozenset({"metron-api", "metronapi"}),
        "metron-api.json",
        MetronApiTransform,
        lexer="json",
        enabled=False,
    )
    COMICVINE_API = MetadataFormat(
        "ComicVine API",
        frozenset({"comicvine-api", "cv-api", "comicvineapi"}),
        "comicvine-api.json",
        ComicVineApiTransform,
        lexer="json",
        enabled=False,
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
        frozenset({"cli", "comicbox-cli"}),
        "comicbox-cli.yaml",
        ComicboxCLITransform,
        has_pages=True,
        lexer="yaml",
    )
