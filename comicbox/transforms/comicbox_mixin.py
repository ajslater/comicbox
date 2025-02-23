"""Comicbox Transform Mixin."""

from comicbox.schemas.comicbox_mixin import STORIES_KEY


class ComicboxTransformMixin:
    """Comicbox Transform Mixin."""

    LIST_KEYS = frozenset({STORIES_KEY})
