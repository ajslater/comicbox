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
    ComicboxSchemaMixin,
)
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbookinfo.credits import cbi_credits_transform
from comicbox.transforms.comicbox.name_objs import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.publishing_tags import (
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_COUNT_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map

TAGGER_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{TAGGER_KEY}"
UPDATED_AT_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{UPDATED_AT_KEY}"


def _to_cb_issue_transform(_source_data, issue_number):
    return str(issue_number)


def issue_transform(issue_tag):
    """Transform cbi integer issues to comicbox issue str and copy the issue number."""
    return KeyTransforms(
        key_map={issue_tag: ISSUE_KEY},
        to_cb=_to_cb_issue_transform,
    )


class ComicBookInfoTransform(BaseTransform):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "appID": TAGGER_KEY_PATH,
                "lastModified": UPDATED_AT_KEY_PATH,
            },
            inherit_root_key_path=False,
        ),
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
            },
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
        format_root_key_path=ComicBookInfoSchema.ROOT_KEY_PATH,
    )
