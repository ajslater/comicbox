"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import STORIES_KEY
from comicbox.transforms.spec import MetaSpec

TITLE_STORIES_DELIMITER = ";"


def title_to_stories(title):
    """Split titles into stories."""
    names = title.split(TITLE_STORIES_DELIMITER)
    return {
        stripped_name: {} for name in names if name and (stripped_name := name.strip())
    }


def stories_to_title(stories):
    """Join stories into a title."""
    names = [story for story in stories if story]
    return TITLE_STORIES_DELIMITER.join(names)


def stories_key_transform_to_cb(title_tag):
    """Create a key transformer for a title tag."""
    return MetaSpec(
        key_map={STORIES_KEY: title_tag},
        spec=title_to_stories,
    )


def stories_key_transform_from_cb(title_tag):
    """Create a key transformer for a title tag."""
    return MetaSpec(
        key_map={title_tag: STORIES_KEY},
        spec=stories_to_title,
    )
