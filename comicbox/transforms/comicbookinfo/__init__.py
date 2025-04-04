"""Comic Book Info transform to and from Comicbox format."""

from bidict import frozenbidict

from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox_mixin import (
    COUNTRY_KEY,
    CRITICAL_RATING_KEY,
    DAY_KEY,
    GENRES_KEY,
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
from comicbox.transforms.comicbookinfo.credits import (
    cbi_credits_primary_to_cb,
    cbi_credits_transform_from_cb,
    cbi_credits_transform_to_cb,
)

# from comicbox.transforms.comicbookinfo.issue import (
#    issue_transform_from_cb,
#    issue_transform_to_cb,
# ) TODO remove
from comicbox.transforms.comicbox import ISSUE_NAME_KEYPATH
from comicbox.transforms.comicbox.name_objs import name_obj_from_cb, name_obj_to_cb
from comicbox.transforms.publishing_tags import (
    ISSUE_COUNT_KEY_PATH,
    PUBLISHER_NAME_KEY_PATH,
    SERIES_NAME_KEY_PATH,
    VOLUME_COUNT_KEY_PATH,
    VOLUME_NUMBER_KEY_PATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)
from comicbox.transforms.stories import (
    stories_key_transform_from_cb,
    stories_key_transform_to_cb,
)

TAGGER_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{TAGGER_KEY}"
UPDATED_AT_KEY_PATH = f"{ComicboxSchemaMixin.ROOT_KEY_PATH}.{UPDATED_AT_KEY}"


TOP_KEYPATHS = frozenbidict(
    {
        "appID": TAGGER_KEY_PATH,
        "lastModified": UPDATED_AT_KEY_PATH,
    }
)
SIMPLE_KEYPATHS = frozenbidict(
    {
        "comments": SUMMARY_KEY,
        "country": COUNTRY_KEY,
        "issue": ISSUE_NAME_KEYPATH,
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
    }
)
NAME_OBJ_KEYPATHS = frozenbidict(
    {
        "genre": GENRES_KEY,
        "tags": TAGS_KEY,
    }
)


class ComicBookInfoTransform(BaseTransform):
    """Comic Book Info transform."""

    SCHEMA_CLASS = ComicBookInfoSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(
            key_map=TOP_KEYPATHS.inverse,
            inherit_root_keypath=False,
        ),
        MetaSpec(
            key_map=SIMPLE_KEYPATHS.inverse,
        ),
        cbi_credits_transform_to_cb("credits"),
        cbi_credits_primary_to_cb("credits"),
        # issue_transform_to_cb(), TODO remove
        name_obj_to_cb(NAME_OBJ_KEYPATHS.inverse),
        stories_key_transform_to_cb("title"),
        format_root_keypath=ComicBookInfoSchema.ROOT_KEY_PATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(
            key_map=TOP_KEYPATHS,
            inherit_root_keypath=False,
        ),
        MetaSpec(
            key_map=SIMPLE_KEYPATHS,
        ),
        cbi_credits_transform_from_cb("credits"),
        # issue_transform_from_cb(), TODO remove
        name_obj_from_cb(NAME_OBJ_KEYPATHS),
        stories_key_transform_from_cb("title"),
        format_root_keypath=ComicBookInfoSchema.ROOT_KEY_PATH,
    )
