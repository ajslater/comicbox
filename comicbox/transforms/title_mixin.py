"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import STORIES_KEY


class TitleStoriesMixin:
    """Title to Stories Transform Mixin."""

    TITLE_TAG = ""
    TITLE_STORIES_DELIMITER = ";"

    def parse_stories(self, data):
        """Parse Title into Stories."""
        if title := data.get(self.TITLE_TAG):
            names = title.split(self.TITLE_STORIES_DELIMITER)
            if stories := {
                stripped_name: {}
                for name in names
                if name and (stripped_name := name.strip())
            }:
                data[STORIES_KEY] = stories
        return data

    def unparse_stories(self, data):
        """Unparse Stories into Title."""
        if stories := data.get(STORIES_KEY):
            names = [story for story in stories if story]
            if title := self.TITLE_STORIES_DELIMITER.join(names):
                data[self.TITLE_TAG] = title
        return data
