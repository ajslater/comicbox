"""Comicbox Transform Mixin."""

from types import MappingProxyType

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, STORIES_KEY, TAGGER_KEY


class ComicboxTransformMixin:
    """Comicbox Transform Mixin."""

    LIST_KEYS = frozenset({STORIES_KEY})
    TOP_TAG_MAP = MappingProxyType({TAGGER_KEY: APP_ID_KEY})
