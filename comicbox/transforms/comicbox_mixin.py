"""Comicbox Transform Mixin."""

from types import MappingProxyType

from comicbox.schemas.comicbox_mixin import (
    COLORIST_KEY,
    COVER_ARTIST_KEY,
    CREATOR_KEY,
    EDITOR_KEY,
    INKER_KEY,
    LETTERER_KEY,
    PENCILLER_KEY,
    WRITER_KEY,
)


class ComicboxTransformMixin:
    """Comicbox Transform Mixin."""

    CONTRIBUTOR_COMICBOX_MAP = MappingProxyType(
        {
            # This could be expanded to encompass all possible roles like in metron
            COLORIST_KEY: COLORIST_KEY,
            COVER_ARTIST_KEY: COVER_ARTIST_KEY,
            CREATOR_KEY: CREATOR_KEY,
            EDITOR_KEY: EDITOR_KEY,
            INKER_KEY: INKER_KEY,
            LETTERER_KEY: LETTERER_KEY,
            PENCILLER_KEY: PENCILLER_KEY,
            WRITER_KEY: WRITER_KEY,
        }
    )
    CONTRIBUTOR_SCHEMA_MAP = CONTRIBUTOR_COMICBOX_MAP
