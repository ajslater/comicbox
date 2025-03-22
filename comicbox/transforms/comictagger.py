"""Comictagger transform to and from Comicbox format."""

from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COUNTRY_KEY,
    DAY_KEY,
    GENRES_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    MONOCHROME_KEY,
    MONTH_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PAGE_INDEX_KEY,
    SERIES_GROUPS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    YEAR_KEY,
)
from comicbox.schemas.comictagger import (
    STORY_ARC_TAG,
    ComictaggerSchema,
)
from comicbox.transforms.base import (
    name_obj_to_string_list_key_transforms,
)
from comicbox.transforms.comet_reprints import comet_reprints_transform
from comicbox.transforms.comicbookinfo_credits import cbi_credits_transform
from comicbox.transforms.comicinfo_pages import comicinfo_pages_transform
from comicbox.transforms.comicinfo_storyarcs import story_arcs_transform
from comicbox.transforms.comictagger_identifiers import (
    COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM,
    COMICTAGGER_IDENTIFIERS_TRANSFORM,
    COMICTAGGER_ISSUE_ID_TRANSFORM,
    COMICTAGGER_SERIES_ID_TRANSFORM,
    COMICTAGGER_URLS_TRANSFORM,
)
from comicbox.transforms.comictagger_reprints import (
    CT_SERIES_ALIASES_KEY_TRANSFORM,
    CT_TITLE_ALIASES_KEY_TRANSFORM,
)
from comicbox.transforms.json_transforms import JsonTransform
from comicbox.transforms.price import price_key_transform
from comicbox.transforms.publishing_tags import (
    IMPRINT_NAME_KEY_PATH,
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_COUNT_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.stories import stories_key_transform
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map

_PAGE_TRANSFORM_MAP = create_transform_map(
    KeyTransforms(
        key_map={
            "Image": PAGE_INDEX_KEY,
            "Type": "page_type",
            "DoublePage": "double_page",
            "ImageSize": "size",
            "Key": "key",
            "Bookmark": "bookmark",
            "ImageWidth": "width",
            "ImageHeight": "height",
        }
    )
)


class ComictaggerTransform(JsonTransform):
    """Comictagger transform."""

    SCHEMA_CLASS = ComictaggerSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "black_and_white": MONOCHROME_KEY,
                "country": COUNTRY_KEY,
                "day": DAY_KEY,
                "description": SUMMARY_KEY,
                "format": ORIGINAL_FORMAT_KEY,
                "imprint": IMPRINT_NAME_KEY_PATH,
                "issue": ISSUE_KEY,
                "issue_count": ISSUE_COUNT_KEY_PATH,
                "language": LANGUAGE_KEY,
                "maturity_rating": AGE_RATING_KEY,
                "month": MONTH_KEY,
                "notes": NOTES_KEY,
                "page_count": PAGE_COUNT_KEY,
                "publisher": PUBLISHER_NAME_KEY_PATH,
                "series": SERIES_NAME_KEY_PATH,
                "volume_count": VOLUME_COUNT_KEY_PATH,
                "volume": VOLUME_NUMBER_KEY_PATH,
                "year": YEAR_KEY,
            }
        ),
        cbi_credits_transform("credits"),
        name_obj_to_string_list_key_transforms(
            {
                "characters": CHARACTERS_KEY,
                "genres": GENRES_KEY,
                "locations": LOCATIONS_KEY,
                "series_group": SERIES_GROUPS_KEY,
                "tags": TAGS_KEY,
                "teams": TEAMS_KEY,
            }
        ),
        COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM,
        COMICTAGGER_IDENTIFIERS_TRANSFORM,
        COMICTAGGER_ISSUE_ID_TRANSFORM,
        COMICTAGGER_SERIES_ID_TRANSFORM,
        comicinfo_pages_transform("pages", _PAGE_TRANSFORM_MAP),
        price_key_transform("price"),
        comet_reprints_transform("is_version_of"),
        CT_SERIES_ALIASES_KEY_TRANSFORM,
        CT_TITLE_ALIASES_KEY_TRANSFORM,
        stories_key_transform("title"),
        story_arcs_transform(STORY_ARC_TAG, ""),
        COMICTAGGER_URLS_TRANSFORM,
        format_root_key_path_path=ComictaggerSchema.ROOT_KEY_PATH,
    )
