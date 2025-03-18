"""Comictagger Aliases to reprints."""

from comicbox.schemas.comicbox_mixin import (
    NAME_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    STORIES_KEY,
)
from comicbox.schemas.comictagger import SERIES_ALIASES_TAG, TITLE_ALIASES_TAG
from comicbox.transforms.transform_map import KeyTransforms


def _series_aliases_to_reprints(_source_data, series_aliases):
    reprints = []
    for series_alias in series_aliases:
        if series_alias:
            reprint = {SERIES_KEY: {NAME_KEY: series_alias}}
            reprints.append(reprint)
    return reprints


def _reprints_to_series_aliases(_source_data, reprints):
    series_aliases = set()
    for reprint in reprints:
        if series_name := reprint.get(SERIES_KEY, {}).get(NAME_KEY):
            series_aliases.add(series_name)
    return series_aliases


def _title_aliases_to_reprints(_source_data, title_aliases):
    reprints = []
    for title_alias in title_aliases:
        if stories := title_alias.split(",;"):
            reprint = {STORIES_KEY: stories}
            reprints.append(reprint)
    return reprints


def _reprints_to_title_aliases(_source_data, reprints):
    title_aliases = set()
    for reprint in reprints:
        if story_names := reprint.get(STORIES_KEY, {}).keys():
            title = ";".join(story_names)
            title_aliases.add(title)
    return title_aliases


CT_SERIES_ALIASES_KEY_TRANSFORM = KeyTransforms(
    key_map={
        SERIES_ALIASES_TAG: REPRINTS_KEY,
    },
    to_cb=_series_aliases_to_reprints,
    from_cb=_reprints_to_series_aliases,
)


CT_TITLE_ALIASES_KEY_TRANSFORM = KeyTransforms(
    key_map={
        TITLE_ALIASES_TAG: REPRINTS_KEY,
    },
    to_cb=_title_aliases_to_reprints,
    from_cb=_reprints_to_title_aliases,
)
