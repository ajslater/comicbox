"""Generic Role enums."""

from enum import Enum


class GenericRoleEnum(Enum):
    """Generic acceptable roles."""

    AUTHOR = "Author"
    COLOURIST = "Colourist"
    PAINTER = "Painter"


class GenericRoleAliases(Enum):
    """Generic Role Aliases."""

    COLORIST = (
        "colorer",
        "colourer",
        "colors",
        "colours",
    )
    COVER = ("covers",)
    EDITOR = ("edits", "editing")
    INKER = ("finishes", "inks")
    LETTERER = ("letters",)
    PAINTER = ("painting", "painter")
    PENCILLER = ("breakdowns", "pencils")
    TRANSLATOR = ("translation",)
    WRITER = ("plotter", "scripter", "script")
