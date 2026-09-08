"""Manga/reading direction split and canonical age ratings."""

import pytest

from comicbox.enums.comicbox import MangaEnum, ReadingDirectionEnum
from comicbox.formats.base.fields.enum_fields import AgeRatingField
from comicbox.formats.comic_info.transform import ComicInfoTransform

_TRANSFORM = ComicInfoTransform(None)
_AGE_RATING_FIELD = AgeRatingField()


def _to_cb(manga: str) -> dict:
    return dict(_TRANSFORM.to_comicbox({"ComicInfo": {"Manga": manga}})["comicbox"])


def _from_cb(**comicbox_md: str) -> str | None:
    comicinfo = _TRANSFORM.from_comicbox({"comicbox": comicbox_md}).get("ComicInfo", {})
    manga = comicinfo.get("Manga")
    return manga.value if manga is not None else None


@pytest.mark.parametrize(
    ("comicinfo_manga", "manga", "reading_direction"),
    [
        ("Yes", MangaEnum.YES, None),
        # The compound value carries both facts and must split into both.
        ("YesAndRightToLeft", MangaEnum.YES, ReadingDirectionEnum.RTL),
        ("No", MangaEnum.NO, None),
        # Unknown used to be coerced to No, asserting a book was not manga
        # when the file said it didn't know.
        ("Unknown", MangaEnum.UNKNOWN, None),
    ],
)
def test_manga_splits_on_read(
    comicinfo_manga: str,
    manga: MangaEnum,
    reading_direction: ReadingDirectionEnum | None,
) -> None:
    """ComicInfo's compound Manga tag splits across two comicbox fields."""
    sub_md = _to_cb(comicinfo_manga)
    assert sub_md.get("manga") == manga
    assert sub_md.get("reading_direction") == reading_direction


@pytest.mark.parametrize(
    ("comicbox_md", "expected"),
    [
        ({"manga": "Yes", "reading_direction": "rtl"}, "YesAndRightToLeft"),
        ({"manga": "Yes", "reading_direction": "ltr"}, "Yes"),
        ({"manga": "Yes"}, "Yes"),
        ({"manga": "No"}, "No"),
        ({"manga": "Unknown"}, "Unknown"),
        # A reading direction alone says nothing about being manga.
        ({"reading_direction": "rtl"}, None),
    ],
)
def test_manga_recomposes_on_write(comicbox_md: dict, expected: str | None) -> None:
    """Writing ComicInfo rebuilds the compound tag from both fields."""
    assert _from_cb(**comicbox_md) == expected


@pytest.mark.parametrize("comicinfo_manga", ["Yes", "YesAndRightToLeft", "No"])
def test_manga_round_trips(comicinfo_manga: str) -> None:
    """A ComicInfo Manga value survives read and write unchanged."""
    sub_md = _to_cb(comicinfo_manga)
    assert _from_cb(**sub_md) == comicinfo_manga


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # MetronInfo's own scale is the fixed point.
        ("Teen", "Teen"),
        ("Teen Plus", "Teen Plus"),
        ("Mature", "Mature"),
        ("Explicit", "Explicit"),
        ("Adult", "Adult"),
        ("Everyone", "Everyone"),
        # ComicInfo's finer scale coarsens onto it.
        ("Everyone 10+", "Everyone"),
        ("G", "Everyone"),
        ("Kids to Adults", "Everyone"),
        ("Early Childhood", "Everyone"),
        ("MA15+", "Teen Plus"),
        ("Mature 17+", "Mature"),
        ("R18+", "Mature"),
        ("X18+", "Explicit"),
        ("Adults Only 18+", "Adult"),
        ("Rating Pending", "Unknown"),
        # Publisher schemes resolve too.
        ("T+", "Teen Plus"),
        ("13+", "Teen"),
        ("Parental Advisory", "Teen Plus"),
        ("Max", "Mature"),
        ("Max: Explicit Content", "Explicit"),
    ],
)
def test_age_rating_canonicalizes(value: str, expected: str) -> None:
    """Every age rating scheme is stored on MetronInfo's scale."""
    assert _AGE_RATING_FIELD.deserialize(value) == expected


def test_unknown_age_rating_passes_through() -> None:
    """An unrecognized rating stays readable rather than being dropped."""
    assert _AGE_RATING_FIELD.deserialize("Bananas") == "Bananas"
