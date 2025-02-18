"""ComicInfo Age Rating Transform Mixin."""

from bidict import frozenbidict

from comicbox.schemas.comicbox_mixin import AGE_RATING_KEY
from comicbox.schemas.comicinfo import ComicInfoAgeRatingEnum
from comicbox.schemas.metroninfo import MetronAgeRatingEnum


class ComicInfoAgeRatingTransform:
    """ComicInfo Age Rating Transform Mixin."""

    AGE_RATING_TAG = "AgeRating"
    AGE_RATING_MAP = frozenbidict(
        {
            MetronAgeRatingEnum.EVERYONE: ComicInfoAgeRatingEnum.EVERYONE,
            MetronAgeRatingEnum.TEEN: ComicInfoAgeRatingEnum.TEEN,
            MetronAgeRatingEnum.TEEN_PLUS: ComicInfoAgeRatingEnum.MA_15_PLUS,
            MetronAgeRatingEnum.MATURE: ComicInfoAgeRatingEnum.MA_17_PLUS,
            MetronAgeRatingEnum.EXPLICIT: ComicInfoAgeRatingEnum.R_18_PLUS,
            MetronAgeRatingEnum.ADULT: ComicInfoAgeRatingEnum.X_18_PLUS,
        }
    )

    def parse_age_rating(self, data: dict) -> dict:
        """Parse age rating from other types."""
        if age_rating_enum := data.get(self.AGE_RATING_TAG):
            data[AGE_RATING_KEY] = age_rating_enum.value
        return data

    def unparse_age_rating(self, data: dict) -> dict:
        """Unparse string age rating into enum."""
        if age_rating := data.get(AGE_RATING_KEY):
            cix_enum = None
            try:
                cix_enum = ComicInfoAgeRatingEnum(age_rating)
            except ValueError:
                try:
                    mar_enum = MetronAgeRatingEnum(age_rating)
                    cix_enum = self.AGE_RATING_MAP.get(mar_enum)
                except ValueError:
                    pass
            if cix_enum:
                data[self.AGE_RATING_TAG] = cix_enum
        return data
