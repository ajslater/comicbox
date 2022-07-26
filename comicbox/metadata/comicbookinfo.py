"""A class to encapsulate the ComicBookInfo data."""
from datetime import datetime
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
    FILENAME = "ComicBookInfo.json"
    CREDIT_PRIMARY_YES_VALUES = ("yes", "true")

    def _get_credit(self, credit):
        person = credit.get("person")
        if not person:
            return
        role = credit.get("role")
        primary = credit.get("primary")
        try:
            if (
                isinstance(primary, str)
                and primary.lower() in self.CREDIT_PRIMARY_YES_VALUES
            ):
                primary = True
            else:
                primary = bool(primary)
        except Exception:
            primary = False
        self._add_credit(person, role, primary)

    def _from_json_tags(self, root):
        for from_key, to_key in self.JSON_KEYS.items():
            try:
                val = root.get(from_key)
                if val is None:
                    continue

                if from_key == "credits":
                    for credit in val:
                        self._get_credit(credit)
                elif to_key in self.ISSUE_TAGS:
                    val = self.parse_issue(val)
                elif to_key in self.INT_TAGS:
                    val = int(val)
                elif to_key in self.STR_SET_TAGS:
                    if isinstance(val, list):
                        val = frozenset(val)
                    else:
                        val = frozenset([item.strip() for item in val.split(",")])
                    if len(val) == 0:
                        continue
                elif to_key in self.DECIMAL_TAGS:
                    val = self.parse_decimal(val)
                elif to_key in self.PYCOUNTRY_TAGS:
                    val = self._pycountry(to_key, val)
                    if not val:
                        continue
                elif isinstance(val, str):
                    val = val.strip()
                    if not val:
                        continue
                elif isinstance(val, list):
                    # tags
                    if len(val) == 0:
                        continue
                self.metadata[to_key] = val
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
            "lastModified": str(datetime.now()),
            self.ROOT_TAG: cbi,
        }

        for json_key, md_key in self.JSON_KEYS.items():
            try:
                val = self.metadata.get(md_key)
                if not val:
                    continue
                elif md_key in self.DECIMAL_TAGS:
                    if val % 1 == 0:
                        val = int(val)
                    else:
                        val = float(val)
                elif md_key in self.STR_SET_TAGS:
                    val = ",".join(sorted(val))
                elif md_key in self.PYCOUNTRY_TAGS:
                    val = self._pycountry(md_key, val, False)
                    if not val:
                        continue
                cbi[json_key] = val
            except Exception as exc:
                LOG.warning(f"{self.path} CBI serializing {json_key}: {exc}")

        return json_obj
