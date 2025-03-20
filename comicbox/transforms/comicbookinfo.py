"""Comic Book Info transform to and from Comicbox format."""

from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox_mixin import (
    COUNTRY_KEY,
    CRITICAL_RATING_KEY,
    DAY_KEY,
    GENRES_KEY,
    ISSUE_KEY,
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
from comicbox.transforms.comicbookinfo_credits import cbi_credits_transform
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


def _to_cb_issue_transform(_source_data, issue_number):
    return str(issue_number)


def issue_transform(issue_tag):
    """Transform cbi integer issues to comicbox issue str and copy the issue number."""
    return KeyTransforms(
        key_map={issue_tag: ISSUE_KEY},
        to_cb=_to_cb_issue_transform,
    )


class ComicBookInfoTransform(
    JsonTransform,
):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    TOP_TAG_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "appID": TAGGER_KEY,
                "lastModified": UPDATED_AT_KEY,
            }
        ),
    )
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "comments": SUMMARY_KEY,
                "country": COUNTRY_KEY,
                # "issue": ISSUE_KEY
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
                    for key in (
                        # "credits",
                        "tagger",
                        "updated_at",
                    )
                },
            }
        ),
        cbi_credits_transform("credits"),
        issue_transform("issue"),
        name_obj_to_string_list_key_transforms(
            {
                "genre": GENRES_KEY,
                "tags": TAGS_KEY,
            }
        ),
        stories_key_transform("title"),
    )
    TO_COMICBOX_PRE_TRANSFORM = (*JsonTransform.TO_COMICBOX_PRE_TRANSFORM,)
    FROM_COMICBOX_PRE_TRANSFORM = (*JsonTransform.FROM_COMICBOX_PRE_TRANSFORM,)
