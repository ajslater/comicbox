"""Comic Book Info transform to and from Comicbox format."""

from decimal import Decimal
from math import ceil, floor

from comicbox.schemas.comicbookinfo import (
    CREDITS_TAG,
    ComicBookInfoSchema,
)
from comicbox.schemas.comicbox_mixin import (
    COUNTRY_KEY,
    CRITICAL_RATING_KEY,
    DAY_KEY,
    GENRES_KEY,
    ISSUE_KEY,
    ISSUE_NUMBER_KEY,
    LANGUAGE_KEY,
    MONTH_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
    YEAR_KEY,
)
from comicbox.transforms.base import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.comicbookinfo_credits import ComicBookInfoCreditsTransformMixin
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.publishing_tags import (
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_COUNT_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map


class ComicBookInfoTransform(
    ComicBookInfoCreditsTransformMixin,
    JsonTransform,
):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "comments": SUMMARY_KEY,
                "country": COUNTRY_KEY,
                "language": LANGUAGE_KEY,
                "numberOfIssues": ISSUE_COUNT_KEY_PATH,
                "numberOfVolumes": VOLUME_COUNT_KEY_PATH,
                "pages": PAGE_COUNT_KEY,
                "publicationDay": DAY_KEY,
                "publicationMonth": MONTH_KEY,
                "publicationYear": YEAR_KEY,
                "publisher": PUBLISHER_NAME_KEY_PATH,
                "rating": CRITICAL_RATING_KEY,
                "series": SERIES_NAME_KEY_PATH,
                "volume": VOLUME_NUMBER_KEY_PATH,
                **{
                    key: key
                    for key in {
                        "credits",
                        "genres",
                        "issue",
                        "issue_number",
                        "tagger",
                        "updated_at",
                    }
                    | {"genre"}
                },
            }
        ),
        name_obj_to_string_list_key_transforms(
            {
                "genre": GENRES_KEY,
                "tags": TAGS_KEY,
            }
        ),
        stories_key_transform("title"),
    )
    CREDITS_TAG = CREDITS_TAG
    ISSUE_TAG = "issue"
    TAGGER_TAG = "appID"
    UPDATED_AT_TAG = "lastModified"
    TOP_TAG_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                TAGGER_TAG: TAGGER_KEY,
                UPDATED_AT_TAG: UPDATED_AT_KEY,
            }
        ),
    )

    # TODO replace with "issue": ISSUE_NUMBER_KEY
    # probably don't need a cast.
    # TODO make sure compute handles issue_number with no issue.
    def parse_issue(self, data) -> dict:
        """Parse Issue integer."""
        issue_number = data.get(self.ISSUE_TAG)
        if issue_number is None:
            return data
        data[ISSUE_KEY] = str(issue_number)
        data[ISSUE_NUMBER_KEY] = Decimal(issue_number)
        return data

    def unparse_issue(self, data: dict) -> dict:
        """Parse Issue into an integer."""
        issue_number = data.get(ISSUE_NUMBER_KEY)
        if issue_number is None:
            return data
        # Discard decimal places
        issue_number = floor(issue_number) if issue_number >= 0 else ceil(issue_number)
        data[self.ISSUE_TAG] = issue_number
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.parse_credits,
        parse_issue,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicBookInfoCreditsTransformMixin.unparse_credits,
        unparse_issue,
    )
