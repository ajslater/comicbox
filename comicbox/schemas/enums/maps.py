"""Enum Maps."""

from enum import Enum
from types import MappingProxyType

from comicbox.schemas.enums.age_rating import (
    DCAgeRatingEnum,
    GenericAgeRatingEnum,
    MarvelAgeRatingEnum,
)
from comicbox.schemas.enums.comet import CoMetRoleTagEnum
from comicbox.schemas.enums.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.enums.comicinfo import (
    ComicInfoAgeRatingEnum,
    ComicInfoRoleTagEnum,
)
from comicbox.schemas.enums.metroninfo import (
    GenericFormatEnum,
    MetronAgeRatingEnum,
    MetronFormatEnum,
    MetronRoleEnum,
)
from comicbox.schemas.enums.role import GenericRoleEnum

COMICBOX_ROLE_ALIAS_MAP = MappingProxyType(
    {
        **{enum: enum for enum in CoMetRoleTagEnum},
        **{enum: enum for enum in ComicBookInfoRoleEnum},
        **{enum: enum for enum in ComicInfoRoleTagEnum},
        **{enum: enum for enum in MetronRoleEnum},
        **{enum: enum for enum in GenericRoleEnum},
    }
)


COMICINFO_AGE_RATING_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        MarvelAgeRatingEnum.ALL_AGES: ComicInfoAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.PG: ComicInfoAgeRatingEnum.E_10_PLUS,
        MarvelAgeRatingEnum.PG_PLUS: ComicInfoAgeRatingEnum.E_10_PLUS,
        MarvelAgeRatingEnum.PARENTAL_ADVISORY: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.PSR: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MarvelAgeRatingEnum.PSR_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.A: ComicInfoAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.T_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MarvelAgeRatingEnum.T: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MarvelAgeRatingEnum.EXPLICIT_CONTENT: ComicInfoAgeRatingEnum.X_18_PLUS,
        DCAgeRatingEnum.E: ComicInfoAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.EVERYONE: ComicInfoAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.T: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.TEEN: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.T_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.TEEN_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.M: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.MATURE: ComicInfoAgeRatingEnum.MA_17_PLUS,
        DCAgeRatingEnum.THIRTEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.FIFTEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        DCAgeRatingEnum.SEVENTEEN_PLUS: ComicInfoAgeRatingEnum.MA_17_PLUS,
        GenericAgeRatingEnum.PG13: ComicInfoAgeRatingEnum.MA_15_PLUS,
        GenericAgeRatingEnum.R: ComicInfoAgeRatingEnum.MA_17_PLUS,
        GenericAgeRatingEnum.X: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.XXX: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.ADULT: ComicInfoAgeRatingEnum.A_18_PLUS,
        GenericAgeRatingEnum.PORN: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.PORNOGRAPHY: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.SEX: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.SEXUALLY_EXPLICIT: ComicInfoAgeRatingEnum.X_18_PLUS,
        GenericAgeRatingEnum.VIOLENT: ComicInfoAgeRatingEnum.A_18_PLUS,
        GenericAgeRatingEnum.VIOLENCE: ComicInfoAgeRatingEnum.A_18_PLUS,
        MetronAgeRatingEnum.EVERYONE: ComicInfoAgeRatingEnum.EVERYONE,
        MetronAgeRatingEnum.TEEN: ComicInfoAgeRatingEnum.TEEN,
        MetronAgeRatingEnum.TEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
        MetronAgeRatingEnum.MATURE: ComicInfoAgeRatingEnum.MA_17_PLUS,
        MetronAgeRatingEnum.EXPLICIT: ComicInfoAgeRatingEnum.R_18_PLUS,
        MetronAgeRatingEnum.ADULT: ComicInfoAgeRatingEnum.X_18_PLUS,
    }
)
METRON_AGE_RATING_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        MarvelAgeRatingEnum.ALL_AGES: MetronAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.PG: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.PG_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.PARENTAL_ADVISORY: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.PSR: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.PSR_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.A: MetronAgeRatingEnum.EVERYONE,
        MarvelAgeRatingEnum.T_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        MarvelAgeRatingEnum.T: MetronAgeRatingEnum.TEEN,
        MarvelAgeRatingEnum.EXPLICIT_CONTENT: MetronAgeRatingEnum.EXPLICIT,
        DCAgeRatingEnum.E: MetronAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.EVERYONE: MetronAgeRatingEnum.EVERYONE,
        DCAgeRatingEnum.T: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.TEEN: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.T_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.TEEN_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.M: MetronAgeRatingEnum.MATURE,
        DCAgeRatingEnum.MATURE: MetronAgeRatingEnum.MATURE,
        DCAgeRatingEnum.THIRTEEN_PLUS: MetronAgeRatingEnum.TEEN,
        DCAgeRatingEnum.FIFTEEN_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        DCAgeRatingEnum.SEVENTEEN_PLUS: MetronAgeRatingEnum.MATURE,
        GenericAgeRatingEnum.PG13: MetronAgeRatingEnum.TEEN,
        GenericAgeRatingEnum.R: MetronAgeRatingEnum.MATURE,
        GenericAgeRatingEnum.X: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.XXX: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.ADULT: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.PORN: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.PORNOGRAPHY: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.SEX: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.SEXUALLY_EXPLICIT: MetronAgeRatingEnum.ADULT,
        GenericAgeRatingEnum.VIOLENT: MetronAgeRatingEnum.EXPLICIT,
        GenericAgeRatingEnum.VIOLENCE: MetronAgeRatingEnum.EXPLICIT,
        ComicInfoAgeRatingEnum.EVERYONE: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.EARLY_CHILDHOOD: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.E_10_PLUS: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.G: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.KIDS_TO_ADULTS: MetronAgeRatingEnum.EVERYONE,
        ComicInfoAgeRatingEnum.TEEN: MetronAgeRatingEnum.TEEN,
        ComicInfoAgeRatingEnum.PG: MetronAgeRatingEnum.TEEN,
        ComicInfoAgeRatingEnum.MA_15_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
        ComicInfoAgeRatingEnum.M: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.MA_17_PLUS: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.R_18_PLUS: MetronAgeRatingEnum.MATURE,
        ComicInfoAgeRatingEnum.X_18_PLUS: MetronAgeRatingEnum.EXPLICIT,
        ComicInfoAgeRatingEnum.A_18_PLUS: MetronAgeRatingEnum.ADULT,
    }
)


def _variants(enum, *, dashed_canon=False):
    space = " " if not dashed_canon else "-"
    dash = "-" if not dashed_canon else " "
    return {
        enum.value.replace(space, dash): enum,
        enum.value.replace(space, ""): enum,
        enum.value.replace("'", ""): enum,
        enum.value.replace("'", "").replace(space, dash): enum,
    }


def _all_variants(enums):
    variant_map = {}
    for enum in enums:
        variants = _variants(enum)
        variant_map.update(variants)
    return variant_map


GENERIC_FORMAT_MAP: MappingProxyType[Enum | str, Enum] = MappingProxyType(
    {
        **_all_variants(GenericFormatEnum),
        "Boxed Set": GenericFormatEnum.BOX_SET,
        "GN": GenericFormatEnum.GRAPHIC_NOVEL,
        "HC": GenericFormatEnum.HARD_COVER,
        **_variants(GenericFormatEnum.ONE_SHOT, dashed_canon=True),
        "TBP": GenericFormatEnum.TRADE_PAPERBACK,
        "TP": GenericFormatEnum.TRADE_PAPERBACK,
    }
)


def _translate_generic_to(generic_enum, metron_enum):
    multi_map = {}
    for key, value in GENERIC_FORMAT_MAP.items():
        if value == generic_enum:
            multi_map[key] = metron_enum

    return multi_map


METRON_FORMAT_MAP: MappingProxyType[Enum, Enum] = MappingProxyType(
    {
        # GenericFormatEnum.ANTHOLOGY: MetronFormatEnum.,
        # GenericFormatEnum.ANNOTATION: MetronFormatEnum.,
        **_translate_generic_to(GenericFormatEnum.BOX_SET, MetronFormatEnum.OMNIBUS),
        GenericFormatEnum.DIGITAL: MetronFormatEnum.DIGITAL_CHAPTER,
        # GenericFormatEnum.DIRECTORS_CUT: MetronFormatEnum.,
        # GenericFormatEnum.DIRECTOR_S_CUT: MetronFormatEnum.,
        GenericFormatEnum.GIANT_SIZED: MetronFormatEnum.ANNUAL,
        **_translate_generic_to(
            GenericFormatEnum.GRAPHIC_NOVEL, MetronFormatEnum.GRAPHIC_NOVEL
        ),
        **_translate_generic_to(
            GenericFormatEnum.HARD_COVER, MetronFormatEnum.HARDCOVER
        ),
        GenericFormatEnum.HD_UPSCALED: MetronFormatEnum.DIGITAL_CHAPTER,
        **_translate_generic_to(GenericFormatEnum.KING_SIZED, MetronFormatEnum.ANNUAL),
        # GenericFormatEnum.MAGAZINE: MetronFormatEnum.,
        # GenericFormatEnum.MANGA: MetronFormatEnum.,
        **_translate_generic_to(GenericFormatEnum.ONE_SHOT, MetronFormatEnum.ONE_SHOT),
        # GenericFormatEnum.PDF_RIP: MetronFormatEnum.,
        # GenericFormatEnum.PREVIEW: MetronFormatEnum.,
        # GenericFormatEnum.PROLOGUE: MetronFormatEnum.,
        # GenericFormatEnum.SCANLATION: MetronFormatEnum.,
        # GenericFormatEnum.SCRIPT: MetronFormatEnum.,
        **_translate_generic_to(
            GenericFormatEnum.TRADE_PAPERBACK, MetronFormatEnum.TRADE_PAPERBACK
        ),
        # GenericFormatsEnum.WEB_COMIC: MetronFormatEnum.,
        # GenericFormatsEnum.WEB_RIP: MetronFormatEnum.,
    }
)
