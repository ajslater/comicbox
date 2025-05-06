"""ComicInfo Fields."""

from comicbox.fields.xml_fields import XmlEnumField
from comicbox.schemas.enums.comicinfo import ComicInfoAgeRatingEnum
from comicbox.schemas.enums.maps import COMICINFO_AGE_RATING_MAP


class ComicInfoAgeRatingField(XmlEnumField):
    """Age Rating Field."""

    ENUM = ComicInfoAgeRatingEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = COMICINFO_AGE_RATING_MAP
