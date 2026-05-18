"""Metadata sources definitions."""

from dataclasses import dataclass
from enum import Enum

from comicbox.formats import MetadataFormats


@dataclass
class MetadataSource:
    """Metadata source attributes."""

    label: str
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
            MetadataFormats.FILENAME,
        ),
    )
    ARCHIVE_FILENAME = MetadataSource(
        "Filename", formats=(MetadataFormats.FILENAME,), from_archive=True
    )
    ARCHIVE_PDF = MetadataSource(
        "Archive Header", formats=(MetadataFormats.PDF,), from_archive=True
    )
    ARCHIVE_COMMENT = MetadataSource(
        "Archive Comment",
        formats=(MetadataFormats.COMIC_BOOK_INFO,),
        from_archive=True,
    )
    ARCHIVE_FILE = MetadataSource(
        "Archive File",
        formats=(
            MetadataFormats.COMICBOX_YAML,
            MetadataFormats.COMICBOX_JSON,
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMET,
            MetadataFormats.COMIC_BOOK_INFO,
        ),
        from_archive=True,
    )
    METRON_API = MetadataSource(
        "Metron API",
        formats=(MetadataFormats.METRON_API,),
    )
    COMICVINE_API = MetadataSource(
        "ComicVine API",
        formats=(MetadataFormats.COMICVINE_API,),
    )
    IMPORT_FILE = MetadataSource("Imported File")
    CLI = MetadataSource(
        "Comicbox CLI",
        formats=(
            MetadataFormats.COMICBOX_CLI_YAML,
            MetadataFormats.METRON_INFO,
            MetadataFormats.COMIC_INFO,
            MetadataFormats.COMIC_BOOK_INFO,
            MetadataFormats.PDF,
            MetadataFormats.COMET,
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
            MetadataFormats.FILENAME,
        ),
    )
