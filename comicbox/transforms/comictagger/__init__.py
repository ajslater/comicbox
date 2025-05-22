"""Comictagger transform to and from Comicbox format."""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    AGE_RATING_KEY,
    BOOKMARK_KEY,
    CHARACTERS_KEY,
    COUNTRY_KEY,
    GENRES_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    MONOCHROME_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_BOOKMARK_KEY,
    PAGE_COUNT_KEY,
    PAGE_INDEX_KEY,
    SERIES_GROUPS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    TITLE_KEY,
)
from comicbox.schemas.comictagger import (
    STORY_ARC_TAG,
    ComictaggerSchema,
)
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comet.reprints import comet_reprints_transform_from_cb
from comicbox.transforms.comicbookinfo.credits import (
    cbi_credits_transform_from_cb,
    cbi_credits_transform_to_cb,
)
from comicbox.transforms.comicbox import (
    DAY_KEYPATH,
    ISSUE_NAME_KEYPATH,
    MONTH_KEYPATH,
    YEAR_KEYPATH,
)
from comicbox.transforms.comicbox.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.transforms.comicinfo.pages import (
    comicinfo_bookmark_to_cb,
    comicinfo_pages_from_cb,
    comicinfo_pages_to_cb,
)
from comicbox.transforms.comicinfo.storyarcs import (
    story_arcs_from_cb,
    story_arcs_to_cb,
)
from comicbox.transforms.comictagger.identifiers import (
    COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_FROM_CB,
    COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB,
    COMICTAGGER_IDENTIFIERS_TRANSFORM_FROM_CB,
    COMICTAGGER_IDENTIFIERS_TRANSFORM_TO_CB,
    COMICTAGGER_ISSUE_ID_TRANSFORM_FROM_CB,
    COMICTAGGER_ISSUE_ID_TRANSFORM_TO_CB,
    COMICTAGGER_SERIES_ID_TRANSFORM_FROM_CB,
    COMICTAGGER_SERIES_ID_TRANSFORM_TO_CB,
    COMICTAGGER_URLS_TRANSFORM_FROM_CB,
    COMICTAGGER_URLS_TRANSFORM_TO_CB,
)
from comicbox.transforms.comictagger.reprints import (
    CT_REPRINTS_TRANSFORM_TO_CB,
    CT_SERIES_ALIASES_TRANSFORM_FROM_CB,
)
from comicbox.transforms.price import (
    price_transform_from_cb,
    price_transform_to_cb,
)
from comicbox.transforms.publishing_tags import (
    IMPRINT_NAME_KEYPATH,
    ISSUE_COUNT_KEYPATH,
    PUBLISHER_NAME_KEYPATH,
    SERIES_NAME_KEYPATH,
    VOLUME_COUNT_KEYPATH,
    VOLUME_NUMBER_KEYPATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

IMAGE_TAG = "Image"
BOOKMARK_TAG = "Bookmark"
PAGE_KEY_MAP = frozenbidict(
    {
        IMAGE_TAG: PAGE_INDEX_KEY,
        "Type": "page_type",
        "DoublePage": "double_page",
        "ImageSize": "size",
        "Key": "key",
        BOOKMARK_TAG: PAGE_BOOKMARK_KEY,
        "ImageWidth": "width",
        "ImageHeight": "height",
    }
)

SIMPLE_KEY_MAP = frozenbidict(
    {
        "black_and_white": MONOCHROME_KEY,
        "country": COUNTRY_KEY,
        "day": DAY_KEYPATH,
        "description": SUMMARY_KEY,
        "format": ORIGINAL_FORMAT_KEY,
        "imprint": IMPRINT_NAME_KEYPATH,
        "issue": ISSUE_NAME_KEYPATH,
        "issue_count": ISSUE_COUNT_KEYPATH,
        "language": LANGUAGE_KEY,
        "last_mark": BOOKMARK_KEY,
        "maturity_rating": AGE_RATING_KEY,
        "month": MONTH_KEYPATH,
        "notes": NOTES_KEY,
        "page_count": PAGE_COUNT_KEY,
        "publisher": PUBLISHER_NAME_KEYPATH,
        "series": SERIES_NAME_KEYPATH,
        "title": TITLE_KEY,
        "volume_count": VOLUME_COUNT_KEYPATH,
        "volume": VOLUME_NUMBER_KEYPATH,
        "year": YEAR_KEYPATH,
    }
)
NAME_OBJ_KEY_MAP = frozenbidict(
    {
        "characters": CHARACTERS_KEY,
        "genres": GENRES_KEY,
        "locations": LOCATIONS_KEY,
        "series_group": SERIES_GROUPS_KEY,
        "tags": TAGS_KEY,
        "teams": TEAMS_KEY,
    }
)


class ComictaggerTransform(BaseTransform):
    """Comictagger transform."""

    SCHEMA_CLASS = ComictaggerSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP.inverse),
        name_obj_to_cb(NAME_OBJ_KEY_MAP.inverse),
        cbi_credits_transform_to_cb("credits"),
        COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB,
        COMICTAGGER_IDENTIFIERS_TRANSFORM_TO_CB,
        COMICTAGGER_ISSUE_ID_TRANSFORM_TO_CB,
        COMICTAGGER_SERIES_ID_TRANSFORM_TO_CB,
        comicinfo_pages_to_cb("pages", PAGE_KEY_MAP.inverse),
        comicinfo_bookmark_to_cb("pages", BOOKMARK_TAG, IMAGE_TAG),
        price_transform_to_cb("price"),
        CT_REPRINTS_TRANSFORM_TO_CB,
        story_arcs_to_cb(STORY_ARC_TAG, ""),
        COMICTAGGER_URLS_TRANSFORM_TO_CB,
        format_root_keypath=ComictaggerSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEY_MAP),
        name_obj_from_cb(NAME_OBJ_KEY_MAP),
        cbi_credits_transform_from_cb("credits"),
        COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_FROM_CB,
        COMICTAGGER_IDENTIFIERS_TRANSFORM_FROM_CB,
        COMICTAGGER_ISSUE_ID_TRANSFORM_FROM_CB,
        COMICTAGGER_SERIES_ID_TRANSFORM_FROM_CB,
        comicinfo_pages_from_cb("pages", PAGE_KEY_MAP),
        price_transform_from_cb("price"),
        comet_reprints_transform_from_cb("is_version_of"),
        CT_SERIES_ALIASES_TRANSFORM_FROM_CB,
        *story_arcs_from_cb(STORY_ARC_TAG, ""),
        COMICTAGGER_URLS_TRANSFORM_FROM_CB,
        format_root_keypath=ComictaggerSchema.ROOT_KEYPATH,
    )
