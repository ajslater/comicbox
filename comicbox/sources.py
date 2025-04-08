"""Metadata sources definitions."""

from dataclasses import dataclass
from enum import Enum

from comicbox.formats import MetadataFormats


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
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMIC_BOOK_INFO,
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
        "Archive Comment",
        path=True,
        formats=(MetadataFormats.COMIC_BOOK_INFO,),
        from_archive=True,
    )
    ARCHIVE_FILE = MetadataSource(
        "Archive File",
        path=True,
        formats=(
            MetadataFormats.COMICBOX_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMET,
            MetadataFormats.COMIC_BOOK_INFO,
            MetadataFormats.COMICTAGGER,
        ),
        from_archive=True,
    )
    IMPORT_FILE = MetadataSource("Imported File", path=True)
    CLI = MetadataSource(
        "Comicbox CLI",
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMIC_BOOK_INFO,
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
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMIC_BOOK_INFO,
            MetadataFormats.COMET,
            MetadataFormats.PDF,
            MetadataFormats.PDF_XML,
            MetadataFormats.COMICTAGGER,
            MetadataFormats.FILENAME,
        ),
    )
    EMBEDDED = MetadataSource(
        "Embedded in Other Metadata",
        path=True,
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.FILENAME,
        ),
        from_archive=True,
    )
