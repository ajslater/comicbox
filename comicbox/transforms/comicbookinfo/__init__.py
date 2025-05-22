"""Comic Book Info transform to and from Comicbox format."""

from bidict import frozenbidict

from comicbox.schemas.comicbookinfo import ComicBookInfoSchema
from comicbox.schemas.comicbox import (
    COUNTRY_KEY,
    CRITICAL_RATING_KEY,
    GENRES_KEY,
    LANGUAGE_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    TITLE_KEY,
    UPDATED_AT_KEY,
    ComicboxSchemaMixin,
)
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbookinfo.credits import (
    cbi_credits_primary_to_cb,
    cbi_credits_transform_from_cb,
    cbi_credits_transform_to_cb,
)
from comicbox.transforms.comicbox import (
    DAY_KEYPATH,
    ISSUE_NAME_KEYPATH,
    MONTH_KEYPATH,
    YEAR_KEYPATH,
)
from comicbox.transforms.comicbox.name_objs import name_obj_from_cb, name_obj_to_cb
from comicbox.transforms.publishing_tags import (
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

TAGGER_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{TAGGER_KEY}"
UPDATED_AT_KEYPATH = f"{ComicboxSchemaMixin.ROOT_KEYPATH}.{UPDATED_AT_KEY}"


TOP_KEYPATHS = frozenbidict(
    {
        "appID": TAGGER_KEYPATH,
        "lastModified": UPDATED_AT_KEYPATH,
    }
)
SIMPLE_KEYPATHS = frozenbidict(
    {
        "comments": SUMMARY_KEY,
        "country": COUNTRY_KEY,
        "issue": ISSUE_NAME_KEYPATH,
        "language": LANGUAGE_KEY,
        "numberOfIssues": ISSUE_COUNT_KEYPATH,
        "numberOfVolumes": VOLUME_COUNT_KEYPATH,
        "pages": PAGE_COUNT_KEY,
        "publicationDay": DAY_KEYPATH,
        "publicationMonth": MONTH_KEYPATH,
        "publicationYear": YEAR_KEYPATH,
        "publisher": PUBLISHER_NAME_KEYPATH,
        "rating": CRITICAL_RATING_KEY,
        "series": SERIES_NAME_KEYPATH,
        "title": TITLE_KEY,
        "volume": VOLUME_NUMBER_KEYPATH,
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
        name_obj_to_cb(NAME_OBJ_KEYPATHS.inverse),
        format_root_keypath=ComicBookInfoSchema.ROOT_KEYPATH,
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
        name_obj_from_cb(NAME_OBJ_KEYPATHS),
        format_root_keypath=ComicBookInfoSchema.ROOT_KEYPATH,
    )
