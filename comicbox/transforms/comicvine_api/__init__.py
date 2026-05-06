"""
ComicVine API transform.

Converts a simyan `Issue.model_dump(mode="json")` dict into the
comicbox internal schema. Like `MetronApiTransform`, the field set
here is intentionally a focused subset for v1; richer collection
mappings (characters, teams, story_arcs, creators) follow.

ComicVine quirks vs Metron:

- ``volume`` is what comicbox calls ``series`` (CV's "volume" is what
  the rest of the comic ecosystem calls a series); the transform
  renames.
- ``image`` is a dict of nine sized URLs; we pull ``thumb_url`` for
  the cover (smallest practical size for hashing).
- ``description`` contains HTML; we pass it through and let downstream
  code strip if needed.
"""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    COVER_IMAGE_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.comicvine_api import ComicVineApiSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import (
    COVER_DATE_KEYPATH,
    ISSUE_NAME_KEYPATH,
    STORE_DATE_KEYPATH,
)
from comicbox.transforms.publishing_tags import SERIES_NAME_KEYPATH
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

# Map comicvine-api source keypath → comicbox internal keypath.
SIMPLE_KEYMAP = frozenbidict(
    {
        # Core fields
        "number": ISSUE_NAME_KEYPATH,
        "image.thumb_url": COVER_IMAGE_KEY,
        "description": SUMMARY_KEY,
        "date_last_updated": UPDATED_AT_KEY,
        # Page count is missing on the search response but present on
        # the full Issue. Keep the slot so we can fill it from get().
        "page_count": PAGE_COUNT_KEY,
        # Dates
        "cover_date": COVER_DATE_KEYPATH,
        "store_date": STORE_DATE_KEYPATH,
        # CV's `volume` is comicbox's `series`.
        "volume.name": SERIES_NAME_KEYPATH,
    }
)


class ComicVineApiTransform(BaseTransform):
    """ComicVine API → comicbox internal schema (and back, minimally)."""

    SCHEMA_CLASS = ComicVineApiSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEYMAP.inverse),
        format_root_keypath=ComicVineApiSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEYMAP),
        format_root_keypath=ComicVineApiSchema.ROOT_KEYPATH,
    )
