"""ComicBookInfo enums."""

from enum import Enum


class ComicBookInfoRoleEnum(Enum):
    """ComicBookInfo Roles."""

    # Common but not restricted to
    ARTIST = "Artist"
    COLORER = "Colorer"
    COVER_ARTIST = "Cover Artist"
    EDITOR = "Editor"
    INKER = "Inker"
    LETTERER = "Letterer"
    OTHER = "Other"
    PENCILLER = "Penciller"
    TRANSLATOR = "Translator"
    WRITER = "Writer"
