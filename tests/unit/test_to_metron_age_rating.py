"""Tests for to_metron_age_rating conversion function."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import comicbox.enums.maps.age_rating

import pytest

from comicbox.enums.comicinfo import ComicInfoAgeRatingEnum
from comicbox.enums.generic.age_rating import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)
from comicbox.enums.maps.age_rating import to_metron_age_rating
from comicbox.enums.metroninfo import MetronAgeRatingEnum

METRON_ENUM_PARAMS = [
    (MetronAgeRatingEnum.UNKNOWN, MetronAgeRatingEnum.UNKNOWN),
    (MetronAgeRatingEnum.EVERYONE, MetronAgeRatingEnum.EVERYONE),
    (MetronAgeRatingEnum.TEEN, MetronAgeRatingEnum.TEEN),
    (MetronAgeRatingEnum.TEEN_PLUS, MetronAgeRatingEnum.TEEN_PLUS),
    (MetronAgeRatingEnum.MATURE, MetronAgeRatingEnum.MATURE),
    (MetronAgeRatingEnum.EXPLICIT, MetronAgeRatingEnum.EXPLICIT),
    (MetronAgeRatingEnum.ADULT, MetronAgeRatingEnum.ADULT),
]
MARVEL_ENUM_PARAMS = [
    (MarvelAgeRatingEnum.ALL_AGES, MetronAgeRatingEnum.EVERYONE),
    (MarvelAgeRatingEnum.T, MetronAgeRatingEnum.TEEN),
    (MarvelAgeRatingEnum.T_PLUS, MetronAgeRatingEnum.TEEN_PLUS),
    (MarvelAgeRatingEnum.PARENTAL_ADVISORY, MetronAgeRatingEnum.TEEN_PLUS),
    (MarvelAgeRatingEnum.EXPLICIT_CONTENT, MetronAgeRatingEnum.EXPLICIT),
]
DC_ENUM_PARAMS = [
    (DCAgeRatingEnum.EVERYONE, MetronAgeRatingEnum.EVERYONE),
    (DCAgeRatingEnum.TEEN, MetronAgeRatingEnum.TEEN),
    (DCAgeRatingEnum.TEEN_PLUS, MetronAgeRatingEnum.TEEN_PLUS),
    (DCAgeRatingEnum.MATURE, MetronAgeRatingEnum.MATURE),
]
COMICINFO_ENUM_PARAMS = [
    (ComicInfoAgeRatingEnum.EVERYONE, MetronAgeRatingEnum.EVERYONE),
    (ComicInfoAgeRatingEnum.TEEN, MetronAgeRatingEnum.TEEN),
    (ComicInfoAgeRatingEnum.MA_15_PLUS, MetronAgeRatingEnum.TEEN_PLUS),
    (ComicInfoAgeRatingEnum.MA_17_PLUS, MetronAgeRatingEnum.MATURE),
    (ComicInfoAgeRatingEnum.X_18_PLUS, MetronAgeRatingEnum.EXPLICIT),
    (ComicInfoAgeRatingEnum.A_18_PLUS, MetronAgeRatingEnum.ADULT),
]
GENERIC_ENUM_PARAMS = [
    (GenericAgeRatingEnum.R, MetronAgeRatingEnum.MATURE),
    (GenericAgeRatingEnum.X, MetronAgeRatingEnum.ADULT),
    (GenericAgeRatingEnum.PORN, MetronAgeRatingEnum.ADULT),
]
STRING_PARAMS = [
    ("Everyone", MetronAgeRatingEnum.EVERYONE),
    ("everyone", MetronAgeRatingEnum.EVERYONE),
    ("EVERYONE", MetronAgeRatingEnum.EVERYONE),
    ("Teen", MetronAgeRatingEnum.TEEN),
    ("Teen Plus", MetronAgeRatingEnum.TEEN_PLUS),
    ("teenplus", MetronAgeRatingEnum.TEEN_PLUS),
    ("Mature", MetronAgeRatingEnum.MATURE),
    ("Explicit", MetronAgeRatingEnum.EXPLICIT),
    ("Adult", MetronAgeRatingEnum.ADULT),
    ("All Ages", MetronAgeRatingEnum.EVERYONE),
    ("Parental Advisory", MetronAgeRatingEnum.TEEN_PLUS),
    ("MA15+", MetronAgeRatingEnum.TEEN_PLUS),
    ("ma15+", MetronAgeRatingEnum.TEEN_PLUS),
    ("Mature 17+", MetronAgeRatingEnum.MATURE),
    ("R18+", MetronAgeRatingEnum.MATURE),
    ("X18+", MetronAgeRatingEnum.EXPLICIT),
    ("Adults Only 18+", MetronAgeRatingEnum.ADULT),
]
NONE_PARAMS = [
    "not a rating",
    "",
    "ZZZZZ",
]


@pytest.mark.parametrize(
    ("value", "expected"),
    METRON_ENUM_PARAMS
    + MARVEL_ENUM_PARAMS
    + DC_ENUM_PARAMS
    + COMICINFO_ENUM_PARAMS
    + GENERIC_ENUM_PARAMS
    + STRING_PARAMS,
)
def test_to_metron_age_rating(value: "comicbox.enums.maps.age_rating.MetronAgeRatingEnum", expected: "comicbox.enums.maps.age_rating.MetronAgeRatingEnum") -> None:
    """Test conversion of various age ratings to MetronAgeRatingEnum."""
    assert to_metron_age_rating(value) == expected


@pytest.mark.parametrize("value", NONE_PARAMS)
def test_to_metron_age_rating_unknown(value: str) -> None:
    """Test that unrecognized values return None."""
    assert to_metron_age_rating(value) is None
