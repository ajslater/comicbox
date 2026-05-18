"""
Metadata formats registry.

`MetadataFormats` is assembled from per-format packages (under
`comicbox.formats.<name>`) plus inline declarations for formats not
yet migrated to the format-package layout. Each migrated format
exports a `REGISTRATION: FormatRegistration` from its `__init__.py`.
"""

from enum import Enum

from comicbox.formats._base import MetadataFormat
from comicbox.formats.comet import REGISTRATION as _COMET_REGISTRATION
from comicbox.formats.comic_book_info import (
    REGISTRATION as _COMIC_BOOK_INFO_REGISTRATION,
)
from comicbox.formats.comic_info import REGISTRATION as _COMIC_INFO_REGISTRATION
from comicbox.formats.comicbox import (
    CLI_YAML_REGISTRATION as _COMICBOX_CLI_YAML_REGISTRATION,
)
from comicbox.formats.comicbox import (
    JSON_REGISTRATION as _COMICBOX_JSON_REGISTRATION,
)
from comicbox.formats.comicbox import (
    YAML_REGISTRATION as _COMICBOX_YAML_REGISTRATION,
)
from comicbox.formats.filename import REGISTRATION as _FILENAME_REGISTRATION
from comicbox.formats.metron_api import REGISTRATION as _METRON_API_REGISTRATION
from comicbox.formats.metron_info import REGISTRATION as _METRON_INFO_REGISTRATION
from comicbox.formats.pdf import PDF_REGISTRATION as _PDF_REGISTRATION
from comicbox.formats.pdf import PDF_XML_REGISTRATION as _PDF_XML_REGISTRATION
from comicbox.transforms.comicvine_api import ComicVineApiTransform


class MetadataFormats(Enum):
    """Metadata formats."""

    # The order these are listed is the order of masking. Very important.

    FILENAME = _FILENAME_REGISTRATION.format
    PDF = _PDF_REGISTRATION.format
    PDF_XML = _PDF_XML_REGISTRATION.format
    COMET = _COMET_REGISTRATION.format
    COMIC_BOOK_INFO = _COMIC_BOOK_INFO_REGISTRATION.format
    COMIC_INFO = _COMIC_INFO_REGISTRATION.format
    METRON_INFO = _METRON_INFO_REGISTRATION.format
    METRON_API = _METRON_API_REGISTRATION.format
    COMICVINE_API = MetadataFormat(
        "ComicVine API",
        frozenset({"comicvine-api", "cv-api", "comicvineapi"}),
        "comicvine-api.json",
        ComicVineApiTransform,
        lexer="json",
        enabled=False,
    )
    COMICBOX_YAML = _COMICBOX_YAML_REGISTRATION.format
    COMICBOX_JSON = _COMICBOX_JSON_REGISTRATION.format
    COMICBOX_CLI_YAML = _COMICBOX_CLI_YAML_REGISTRATION.format
