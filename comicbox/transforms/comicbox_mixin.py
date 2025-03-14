"""Comicbox Transform Mixin."""

from bidict import frozenbidict

from comicbox.schemas.comicbox_mixin import APP_ID_KEY, TAGGER_KEY


class ComicboxTransformMixin:
    """Comicbox Transform Mixin."""

    TOP_TAG_MAP = frozenbidict({(APP_ID_KEY, None): (TAGGER_KEY, None)})
