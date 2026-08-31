"""
ComicInfo Manga tag <-> comicbox manga & reading_direction.

ComicInfo compounds two independent facts into one tag: whether the book is
manga, and whether it reads right to left. Comicbox keeps them apart, in
``manga`` and ``reading_direction``, because ``reading_direction`` is a
concept of its own that CoMet supplies for non-manga books too. This module
splits the tag on read and recomposes it on write.
"""

from enum import Enum
from typing import Any

from comicbox.enums.comicbox import MangaEnum, ReadingDirectionEnum
from comicbox.formats.base.fields.enum_fields import ComicInfoMangaEnum
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import (
    MANGA_KEY,
    READING_DIRECTION_KEY,
)

MANGA_TAG = "Manga"
_MANGA_YES_VALUES = frozenset(
    {ComicInfoMangaEnum.YES.value, ComicInfoMangaEnum.YES_RTL.value}
)


def _enum_value(value: Any) -> str | None:
    """Normalize a value the schema may or may not have deserialized yet."""
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


def _manga_to_cb(comicinfo_manga: Any) -> str | None:
    """Read the manga half of the ComicInfo tag."""
    value = _enum_value(comicinfo_manga)
    if value is None:
        return None
    if value in _MANGA_YES_VALUES:
        return MangaEnum.YES.value
    if value == ComicInfoMangaEnum.NO.value:
        return MangaEnum.NO.value
    return MangaEnum.UNKNOWN.value


def _reading_direction_to_cb(comicinfo_manga: Any) -> str | None:
    """
    Read the reading direction half of the ComicInfo tag.

    Only YesAndRightToLeft carries a direction. The other values say nothing
    about it, so they must not overwrite a direction another source supplied.
    """
    if _enum_value(comicinfo_manga) == ComicInfoMangaEnum.YES_RTL.value:
        return ReadingDirectionEnum.RTL.value
    return None


def _manga_from_cb(values: dict[str, Any]) -> str | None:
    """Recompose the ComicInfo tag from both comicbox fields."""
    manga_value = _enum_value(values.get(MANGA_KEY))
    if manga_value is None:
        return None
    if manga_value != MangaEnum.YES.value:
        return manga_value
    if _enum_value(values.get(READING_DIRECTION_KEY)) == ReadingDirectionEnum.RTL.value:
        return ComicInfoMangaEnum.YES_RTL.value
    return ComicInfoMangaEnum.YES.value


COMICINFO_MANGA_TO_CB = MetaSpec(key_map={MANGA_KEY: MANGA_TAG}, spec=_manga_to_cb)
COMICINFO_READING_DIRECTION_TO_CB = MetaSpec(
    key_map={READING_DIRECTION_KEY: MANGA_TAG}, spec=_reading_direction_to_cb
)
COMICINFO_MANGA_FROM_CB = MetaSpec(
    key_map={MANGA_TAG: (MANGA_KEY, READING_DIRECTION_KEY)}, spec=_manga_from_cb
)
