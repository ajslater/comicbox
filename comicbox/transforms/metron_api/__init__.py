"""
Metron API transform.

Converts a mokkari `Issue.model_dump(mode="json")` dict into the
comicbox internal schema. Built on the same `MetaSpec` primitives the
existing format transforms use; the field set is intentionally a
focused subset for M2 — collections (characters, teams, arcs,
credits, identifiers) and richer publishing tags land in follow-up
milestones.

The scope captured in M2 is enough to demonstrate the
`--id metron:N --write metroninfo file.cbz` end-to-end path and
populates the high-value fields most users will notice in
`comicbox -p` output.
"""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    COLLECTION_TITLE_KEY,
    COVER_IMAGE_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.metron_api import MetronApiSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox import (
    COVER_DATE_KEYPATH,
    ISSUE_NAME_KEYPATH,
    STORE_DATE_KEYPATH,
)
from comicbox.transforms.publishing_tags import (
    PUBLISHER_NAME_KEYPATH,
    SERIES_NAME_KEYPATH,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

# Map metron-api source keypath → comicbox internal keypath.
SIMPLE_KEYMAP = frozenbidict(
    {
        # Core fields
        "number": ISSUE_NAME_KEYPATH,
        "image": COVER_IMAGE_KEY,
        "page_count": PAGE_COUNT_KEY,
        "desc": SUMMARY_KEY,
        "collection_title": COLLECTION_TITLE_KEY,
        "modified": UPDATED_AT_KEY,
        # Dates
        "cover_date": COVER_DATE_KEYPATH,
        "store_date": STORE_DATE_KEYPATH,
        # Publishing
        "series.name": SERIES_NAME_KEYPATH,
        "publisher.name": PUBLISHER_NAME_KEYPATH,
    }
)


class MetronApiTransform(BaseTransform):
    """Metron API → comicbox internal schema (and back, minimally)."""

    SCHEMA_CLASS = MetronApiSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=SIMPLE_KEYMAP.inverse),
        format_root_keypath=MetronApiSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=SIMPLE_KEYMAP),
        format_root_keypath=MetronApiSchema.ROOT_KEYPATH,
    )
