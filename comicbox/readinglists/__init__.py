"""
Reading lists: read, combine and write lists of comics in reading order.

Everything codex uses comes from this package. Nothing outside it imports
it at module load, and it imports no network library, so a normal comicbox
run does not pay for it.
"""

from comicbox.exceptions import (
    ReadingListError,
    ReadingListFormatError,
    SmartListError,
)
from comicbox.readinglists.formats import ReadingListFormat
from comicbox.readinglists.registry import (
    ReadingListFormats,
    detect_format,
    get_format,
)
from comicbox.readinglists.schema import (
    DATE_KEY,
    DESCRIPTION_KEY,
    END_YEAR_KEY,
    ENTRIES_KEY,
    ENTRY_TYPE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    LIST_TYPE_KEY,
    NAME_KEY,
    NEXT_KEY,
    NOTES_KEY,
    NUMBER_KEY,
    ORDERED_KEY,
    PREVIOUS_KEY,
    PRIVATE_KEY,
    READING_LIST_KEY,
    SERIES_KEY,
    SOURCE_CURATOR_KEY,
    SOURCE_CURATOR_URL_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_REVISION_KEY,
    SOURCE_URL_KEY,
    SOURCES_KEY,
    START_YEAR_KEY,
    TAGS_KEY,
    VOLUME_KEY,
    SourceKind,
)
from comicbox.readinglists.serialize import (
    ReadingListResult,
    dumps,
    load,
    loads,
    lost_fields,
)

__all__ = (
    "DATE_KEY",
    "DESCRIPTION_KEY",
    "END_YEAR_KEY",
    "ENTRIES_KEY",
    "ENTRY_TYPE_KEY",
    "IDENTIFIERS_KEY",
    "ISSUE_KEY",
    "LIST_TYPE_KEY",
    "NAME_KEY",
    "NEXT_KEY",
    "NOTES_KEY",
    "NUMBER_KEY",
    "ORDERED_KEY",
    "PREVIOUS_KEY",
    "PRIVATE_KEY",
    "READING_LIST_KEY",
    "SERIES_KEY",
    "SOURCES_KEY",
    "SOURCE_CURATOR_KEY",
    "SOURCE_CURATOR_URL_KEY",
    "SOURCE_KEY_KEY",
    "SOURCE_KIND_KEY",
    "SOURCE_REVISION_KEY",
    "SOURCE_URL_KEY",
    "START_YEAR_KEY",
    "TAGS_KEY",
    "VOLUME_KEY",
    "ReadingListError",
    "ReadingListFormat",
    "ReadingListFormatError",
    "ReadingListFormats",
    "ReadingListResult",
    "SmartListError",
    "SourceKind",
    "detect_format",
    "dumps",
    "get_format",
    "load",
    "loads",
    "lost_fields",
)
