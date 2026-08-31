"""Computed Stories and Title Methods."""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from comicbox.box.computed.date import ComicboxComputedDate
from comicbox.formats.comicbox.schema import STORIES_KEY, TITLE_KEY
from comicbox.merge import (
    AdditiveMerger,
    Merger,
)

_TITLE_STORIES_DELIMITER = ";"
_TITLE_STORIES_JOIN_DELIMITER = f"{_TITLE_STORIES_DELIMITER} "


class ComicboxComputedStoriesTitle(ComicboxComputedDate):
    """Computed Stories and Title Methods."""

    def _get_computed_from_stories(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, str] | None:
        """Build a title out of the stories when the book has no title."""
        if sub_data.get(TITLE_KEY):
            # A title the source stated is the title. It used to be
            # overwritten with the joined stories so Metron, which has no
            # title tag, would beat a filename title — but which source wins
            # is the merge order's job, not this one's.
            return None
        stories = sub_data.get(STORIES_KEY)
        if not stories:
            return None
        title = _TITLE_STORIES_JOIN_DELIMITER.join(stories)
        return {TITLE_KEY: title}

    def _get_computed_from_title(
        self, sub_data: dict[str, Any], **_kwargs: Any
    ) -> dict[str, dict] | None:
        """Read the stories out of a title when the book lists none."""
        if sub_data.get(STORIES_KEY):
            return None
        title = sub_data.get(TITLE_KEY)
        if not title:
            return None
        stories = {
            story: {}
            for story in (raw.strip() for raw in title.split(_TITLE_STORIES_DELIMITER))
            if story
        }
        if not stories:
            return None
        return {STORIES_KEY: stories}

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                # Order is important here
                **ComicboxComputedDate.COMPUTED_ACTIONS,
                "from title": (_get_computed_from_title, AdditiveMerger),
                "from stories": (_get_computed_from_stories, AdditiveMerger),
            }
        )
    )
