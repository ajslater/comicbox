"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import STORIES_KEY
from comicbox.transforms.transform_map import KeyTransforms

_TITLE_STORIES_DELIMITER = ";"


def title_to_stories(title):
    """Split titles into stories."""
    names = title.split(_TITLE_STORIES_DELIMITER)
    return {
        stripped_name: {} for name in names if name and (stripped_name := name.strip())
    }


def stories_to_title(stories):
    """Join stories into a title."""
    names = [story for story in stories if story]
    return _TITLE_STORIES_DELIMITER.join(names)


def stories_key_transform(title_tag):
    """Create a key transformer for a title tag."""
    return KeyTransforms(
        key_map={title_tag: STORIES_KEY},
        to_cb=title_to_stories,
        from_cb=stories_to_title,
    )
