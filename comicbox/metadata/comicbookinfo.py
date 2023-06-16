"""A class to encapsulate the ComicBookInfo data."""
from datetime import datetime, timezone
from logging import getLogger

from comicbox.metadata.comic_json import ComicJSON
from comicbox.version import VERSION

# Schema from:
# https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki

LOG = getLogger(__name__)


class ComicBookInfo(ComicJSON):
    """Comic Book Info metadata."""

    ROOT_TAG = "ComicBookInfo/1.0"
    JSON_KEYS = {
        "series": "series",
        "title": "title",
        "issue": "issue",
        "genre": "genres",
        "publisher": "publisher",
        "publicationMonth": "month",
        "publicationYear": "year",
        "numberOfIssues": "issue_count",
        "comments": "comments",
        "volume": "volume",
        "numberOfVolumes": "volume_count",
        "language": "language",
        "country": "country",
        "rating": "critical_rating",
        "tags": "tags",
        "credits": "credits",
        "pages": "page_count",
    }
    KEY_MAP = JSON_KEYS
    FILENAME = "comic-book-info.json"
    CONFIG_KEYS = frozenset(("cb", "cbi", "comicbookinfo"))

    def _get_credit(self, credit):
        person = credit.get("person")
        if not person:
            return
        role = credit.get("role")
        primary = credit.get("primary")
        primary = self.is_truthy(primary)
        self._add_credit(person, role, primary)

    def _from_json_tag(self, from_key, to_key, val):  # noqa C901
        """Parse one json tag."""
        if from_key == "credits":
            for credit in val:
                self._get_credit(credit)
        elif to_key in self.ISSUE_TAGS:
            val = self.parse_issue(val)
        elif to_key in self.INT_TAGS:
            val = self.parse_int(val)
        elif to_key in self.STR_SET_TAGS:
            val = frozenset(val) if isinstance(val, list) else self.parse_str_set(val)
            if not val:
                return
        elif to_key in self.DECIMAL_TAGS:
            val = self.parse_decimal(val)
        elif to_key in self.PYCOUNTRY_TAGS:
            val = self.parse_pycountry(to_key, val)
            if not val:
                return
        elif isinstance(val, str):
            val = val.strip()
            if not val:
                return
        elif isinstance(val, list) and len(val) == 0:
            # tags
            return
        self.metadata[to_key] = val

    def _from_json_tags(self, root):
        for from_key, to_key in self.JSON_KEYS.items():
            try:
                val = root.get(from_key)
                if val is None:
                    continue
                self._from_json_tag(from_key, to_key, val)
            except Exception as exc:
                LOG.warning(f"{self.path} CBI {from_key} {exc}")

    def _from_json(self, json_obj):
        """Parse metadata from string."""
        root = json_obj[self.ROOT_TAG]
        self._from_json_tags(root)

    def _to_json(self):
        """Create the dictionary that we will convert to JSON text."""
        cbi = {}
        json_obj = {
            "appID": f"Comicbox/{VERSION}",
            "lastModified": str(datetime.now(tz=timezone.utc)),
            self.ROOT_TAG: cbi,
        }

        for json_key, md_key in self.JSON_KEYS.items():
            try:
                val = self.metadata.get(md_key)
                if val is None:
                    continue
                if md_key in self.DECIMAL_TAGS:
                    val = float(val)
                elif md_key in self.PYCOUNTRY_TAGS:
                    val = self.serialize_pycountry(md_key, val)
                elif md_key in self.STR_SET_TAGS:
                    val = self.serialize_str_set(val)

                if not self.is_number_or_truthy(val):
                    continue
                cbi[json_key] = val
            except Exception as exc:
                LOG.warning(f"{self.path} CBI serializing {json_key}: {exc}")

        return json_obj
