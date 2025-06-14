"""Computed Stories and Title Methods."""

from collections.abc import Callable
from types import MappingProxyType

from comicbox.box.computed.date import ComicboxComputedDate
from comicbox.merge import (
    AdditiveMerger,
    Merger,
    ReplaceMerger,
)
from comicbox.schemas.comicbox import STORIES_KEY, TITLE_KEY

_TITLE_STORIES_DELIMITER = ";"
_TITLE_STORIES_JOIN_DELIMITER = f"{_TITLE_STORIES_DELIMITER} "


class ComicboxComputedStoriesTitle(ComicboxComputedDate):
    """Computed Stories and Title Methods."""

    def _get_computed_from_stories(self, sub_data, **_kwargs):
        """Parse stories back into title if no title already exists."""
        # Always overwrite title so Metron, which has no title, will override filename
        # titles.
        stories = sub_data.get(STORIES_KEY)
        if not stories:
            return None
        title = _TITLE_STORIES_JOIN_DELIMITER.join(stories)
        return {TITLE_KEY: title}

    def _get_computed_from_title(self, sub_data, **_kwargs):
        """Parse title from stories."""
        title = sub_data.get(TITLE_KEY)
        if not title:
            return None
        new_stories = tuple(
            story.strip() for story in title.split(_TITLE_STORIES_DELIMITER)
        )
        old_stories = sub_data.get(STORIES_KEY, {})
        stories = {}
        for story in new_stories:
            if story not in old_stories:
                stories[story] = {}
        if not stories:
            return None

        return {STORIES_KEY: stories}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                # Order is important here
                **ComicboxComputedDate.COMPUTED_ACTIONS,
                "from title": (_get_computed_from_title, AdditiveMerger),
                "from stories": (_get_computed_from_stories, ReplaceMerger),
            }
        )
    )
