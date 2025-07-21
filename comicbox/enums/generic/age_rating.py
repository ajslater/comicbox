"""Age Rating Enums."""

# https://metron-project.github.io/docs/metroninfo/ratings
from enum import Enum


class MarvelAgeRatingEnum(Enum):
    """Marvel Age Ratings."""

    # 2001
    ALL_AGES = "All Ages"
    PG = "PG"
    PG_PLUS = "PG+"
    PARENTAL_ADVISORY = "Parental Advisory"

    # 2003
    PSR = "PSR"
    PSR_PLUS = "PSR+"

    # 2005
    A = "A"  # All
    T_PLUS = "T+"
    MAX_EXPLICIT_CONTENT = "Max: Explicit Content"
    MAX = "Max"

    # Current (Year?)
    T = "T"
    EXPLICIT_CONTENT = "ExplicitContent"


class DCAgeRatingEnum(Enum):
    """DC Age Ratings."""

    # 2011
    E = "E"
    EVERYONE = "Everyone"
    T = "T"
    TEEN = "Teen"
    T_PLUS = "T+"
    TEEN_PLUS = "Teen Plus"
    M = "M"
    MATURE = "Mature"

    # 2022
    THIRTEEN_PLUS = "13+"
    FIFTEEN_PLUS = "15+"
    SEVENTEEN_PLUS = "17+"


class GenericAgeRatingEnum(Enum):
    """Generic Age Ratings."""

    PG13 = "PG13"
    R = "R"
    X = "X"
    XXX = "XXX"
    ADULT = "Adult"
    PORN = "Porn"
    PORNOGRAPHY = "Pornography"
    SEX = "Sex"
    SEXUALLY_EXPLICIT = "Sexually Explicit"
    VIOLENT = "Violent"
    VIOLENCE = "Violence"
