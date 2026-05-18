"""
Metadata sources definitions.

`MetadataSources` is a static enum: members are declared in the class
body so the type checker can resolve `MetadataSources.METRON_API` etc.
The per-source `formats` tuple is still derived from each format's
`REGISTRATION.sources` declaration — that part remains plugin-driven.
"""

from dataclasses import dataclass
from enum import Enum

from comicbox.formats import FORMAT_REGISTRATIONS, MetadataFormats


@dataclass
class MetadataSource:
    """Metadata source attributes."""

    label: str
    formats: tuple[MetadataFormats, ...] = ()
    from_archive: bool = False


def _formats_for_source(name: str) -> tuple[MetadataFormats, ...]:
    """
    Collect formats whose REGISTRATION declares membership in this source.

    Sorts by per-source priority (declared in `REGISTRATION.sources[name]`).
    """
    pairs = [
        (priority, fmt)
        for fmt, registration in FORMAT_REGISTRATIONS.items()
        if (priority := registration.sources.get(name)) is not None
    ]
    return tuple(fmt for _, fmt in sorted(pairs, key=lambda p: p[0]))


# Sources that accept arbitrary enabled formats (today: IMPORT_FILE for the
# `--import` CLI option, where the file's format is detected at read time).
_ANY_FORMATS: tuple[MetadataFormats, ...] = tuple(
    fmt for fmt in MetadataFormats if fmt.value.enabled
)


class MetadataSources(Enum):
    """Metadata sources, ordered by source-level masking precedence."""

    CONFIG = MetadataSource("Config", _formats_for_source("CONFIG"))
    ARCHIVE_FILENAME = MetadataSource(
        "Filename", _formats_for_source("ARCHIVE_FILENAME"), from_archive=True
    )
    ARCHIVE_PDF = MetadataSource(
        "Archive Header", _formats_for_source("ARCHIVE_PDF"), from_archive=True
    )
    ARCHIVE_COMMENT = MetadataSource(
        "Archive Comment", _formats_for_source("ARCHIVE_COMMENT"), from_archive=True
    )
    ARCHIVE_FILE = MetadataSource(
        "Archive File", _formats_for_source("ARCHIVE_FILE"), from_archive=True
    )
    METRON_API = MetadataSource("Metron API", _formats_for_source("METRON_API"))
    COMICVINE_API = MetadataSource(
        "ComicVine API", _formats_for_source("COMICVINE_API")
    )
    IMPORT_FILE = MetadataSource("Imported File", _ANY_FORMATS)
    CLI = MetadataSource("Comicbox CLI", _formats_for_source("CLI"))
    API = MetadataSource("API", _formats_for_source("API"))
