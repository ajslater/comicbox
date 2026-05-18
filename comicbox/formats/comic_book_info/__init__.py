"""ComicBookInfo format package."""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comic_book_info.transform import ComicBookInfoTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "ComicBookInfo",
        frozenset({"cbi", "cbl", "comicbookinfo", "comicbooklover"}),
        "comic-book-info.json",
        ComicBookInfoTransform,
        lexer="json",
    ),
    sources=MappingProxyType(
        {
            "CONFIG": 3,
            "ARCHIVE_COMMENT": 0,
            "ARCHIVE_FILE": 6,
            "CLI": 3,
            "API": 5,
        }
    ),
)
