"""Original Format enum maps."""

from enum import Enum
from types import MappingProxyType

from comicbox.enums.generic import GenericFormatEnum
from comicbox.enums.metroninfo import MetronFormatEnum


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
        "Boxed-Set": GenericFormatEnum.BOX_SET,
        "GN": GenericFormatEnum.GRAPHIC_NOVEL,
        "Hard-Cover": GenericFormatEnum.HARD_COVER,
        "Hard Cover": GenericFormatEnum.HARD_COVER,
        "HC": GenericFormatEnum.HARD_COVER,
        **_variants(GenericFormatEnum.ONE_SHOT, dashed_canon=True),
        "TPB": GenericFormatEnum.TRADE_PAPERBACK,
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
