"""ComicBookInfo format package."""

from types import MappingProxyType

from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comic_book_info.transform import ComicBookInfoTransform
from comicbox.validate.spec import ValidatorSpec, ValidatorType

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
    validator_spec=ValidatorSpec(
        ValidatorType.JSON, "comic-book-info-v1.0.schema.json"
    ),
    has_tags_without_ids=True,
)
