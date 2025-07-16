"""ComicInfo Fields."""

from comicbox.enums.comicinfo import ComicInfoAgeRatingEnum
from comicbox.enums.maps.age_rating import COMICINFO_AGE_RATING_MAP
from comicbox.fields.xml_fields import XmlEnumField


class ComicInfoAgeRatingField(XmlEnumField):
    """Age Rating Field."""

    ENUM = ComicInfoAgeRatingEnum  # pyright: ignore[reportIncompatibleUnannotatedOverride]
    ENUM_ALIAS_MAP = COMICINFO_AGE_RATING_MAP
