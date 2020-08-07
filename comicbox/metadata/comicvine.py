"""A class to encapsulate the ComicBookInfo data."""
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser

from .comic_dict import ComicDict


PROGRAM_NAME = "comicbox"
# DISTRIBUTION = pkg_resources.get_distribution(PROGRAM_NAME)
VERSION = "HACK IMPORT"  # DISTRIBUTION.version


class ComicVine(ComicDict):
    """ComicVine meatadata."""

    ROOT_TAG = ""
    ISSUE_KEYS = {
        "deck": "description",
        "description": "comments",
        "issue_number": "issue",
        "name": "title",
        "site_detail_url": "web",
    }
    TAG_KEYS = {
        "character_credits": "characters",
        "location_credits": "locations",
        "story_arc_credits": "story_arcs",
        "team_credits": "teams",
    }

    VOLUME_KEYS = {
        "count_of_issues": "issue_count",
        "name": "series",
        "start_year": "name",
    }
    PUBLISHER_KEYS = {"name": "name"}
    FILENAME = "ComicVine.json"
    INT_TAGS = ("issue_count",)
    DECIMAL_TAGS = ("issue",)

    def _from_dict_tags(self, root):
        for from_key, to_key in self.ISSUE_KEYS.items():
            val = root.get(from_key)
            if val is None:
                continue

            if to_key in self.INT_TAGS:
                val = int(val)
            if to_key in self.DECIMAL_TAGS:
                val = self.parse_decimal(val)
            elif isinstance(val, str):
                val = val.strip()
                if not val:
                    continue
            elif isinstance(val, list):
                new_val = []
                for item in val:
                    new_val.append(item.get("name"))
                val = new_val

            self.metadata[to_key] = val

        if root.get("cover_date"):
            cover_date = parser.parse(root.get("cover_date"))
            self.metadata["year"] = cover_date.year
            self.metadata["month"] = cover_date.month
            self.metadata["day"] = cover_date.day

        comments = ""
        if root.get("description"):
            soup = BeautifulSoup(root.get("description"))
            comments += soup.to_text()

        if root.get("deck"):
            soup = BeautifulSoup(root.get("deck"))
            comments += soup.to_text()

        if comments:
            self.metadata["comments"] = comments

    def _from_dict_credits(self, root):
        credits = root.get("person_credits")
        for person in credits:
            self._add_credit(person.get("name"), person.get("role"))

    def _from_dict_volume(self, root):
        for from_key, to_key in self.VOLUME_KEYS.items():
            val = root.get(from_key)
            if val is None:
                continue

            if to_key in self.INT_TAGS:
                val = int(val)
            if isinstance(val, str):
                val = val.strip()
                if not val:
                    continue

            self.metadata[to_key] = val

        publisher = root.get("publisher").get("name")
        if publisher:
            self.metadata["publisher"] = publisher

    def _from_dict(self, obj):
        """Parse metadata from string."""
        root = obj[self.ROOT_TAG]
        self._from_dict_tags(root)
        self._from_dict_credits(root)
        volume = root.get("volume")
        self._from_dict_volume(volume)
        cv_issue_id = root.get("id")
        self.metadata["notes"] = (
            f"Tagged with Comicbox {VERSION} on "
            f"{datetime.now()}. [Issue ID {cv_issue_id}]"
        )
