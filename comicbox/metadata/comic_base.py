"""Metadata class for a comic archive."""
import re

from decimal import Decimal
from logging import getLogger

import pycountry

from deepdiff.diff import DeepDiff


IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)$", re.IGNORECASE)
LOG = getLogger(__name__)


class ComicBaseMetadata:
    """Comicbox Metadata Class."""

    FILENAME = ""

    class ReadingDirection:
        """Reading direction enum."""

        LTR = "ltr"
        RTL = "rtl"

        @classmethod
        def parse(cls, val):
            """Match a reading direction to an acceptable value."""
            val = val.strip().lower()
            if val == cls.RTL:
                return cls.RTL
            elif val == cls.LTR:
                return cls.LTR

    STR_SET_TAGS = frozenset(
        (
            "characters",
            "locations",
            "tags",
            "teams",
            "genres",
            "story_arcs",
            "series_groups",
        )
    )
    BOOL_SET_TAGS = frozenset(("black_and_white",))
    DICT_LIST_TAGS = frozenset(("credits", "pages"))
    PYCOUNTRY_TAGS = frozenset(("country", "language"))
    DECIMAL_TAGS = frozenset(
        (
            "community_rating",
            "critical_rating",
            "price",
        )
    )
    ISSUE_TAGS = frozenset(("issue", "alternate_issue"))
    INT_TAGS = frozenset(
        (
            "day",
            "issue_count",  # cix Count
            "alternate_issue_count",
            "last_mark",
            "month",
            "page_count",
            "volume",
            "volume_count",
            "year",
        )
    )
    VOLUME_PREFIXES = ("volume", "vol.", "vol", "v")
    IGNORE_COMPARE_TAGS = ("ext", "remainder")
    TRUTHY_VALUES = ("yes", "true", "1")
    DECIMAL_MATCHER = re.compile(r"\d*\.?\d+")

    def __init__(self, string=None, path=None, metadata=None):
        """Initialize the metadata dict or parse it from a source."""
        self.metadata = {}
        self._page_filenames = None
        self.path = path
        if metadata is not None:
            self.metadata = metadata
        elif string is not None:
            self.from_string(string)
        elif path is not None:
            self.from_file(path)

    @staticmethod
    def _credit_key(credit):
        """Get a unique key for credits."""
        return f"{credit.get('role')}:{credit.get('person')}".lower()

    @staticmethod
    def _pycountry(tag, name, long_to_alpha2=True):
        """Convert countries and languages to long names or alpha2."""
        if tag == "country":
            module = pycountry.countries
        elif tag == "language":
            module = pycountry.languages
        else:
            raise NotImplementedError(f"no pycountry module for {tag}")
        name = name.strip()
        if not name:
            return
        if len(name) == 2:
            # Language lookup fails for 'en' unless alpha_2 is specified.
            obj = module.get(alpha_2=name)
        else:
            obj = module.lookup(name)

        if obj is None:
            raise ValueError(f"couldn't find {tag} for {name}")

        if long_to_alpha2:
            return obj.alpha_2
        else:
            return obj.name

    @staticmethod
    def decimal_to_type(dec):
        """Return an integer if we can."""
        if dec % 1 == 0:
            return int(dec)
        else:
            return float(dec)

    def __eq__(self, obj):
        """== operator."""
        return bool(DeepDiff(self.metadata, obj.metadata, ignore_order=True))

    @classmethod
    def parse_bool(cls, value):
        """Parse boolean type."""
        return value.lower() in cls.TRUTHY_VALUES

    @classmethod
    def parse_issue(cls, num):
        """Parse issues."""
        num = num.replace(" ", "")

        num = num.lstrip("#")
        num = num.lstrip("0")
        num = num.rstrip(".")
        num = num.replace("½", ".5")
        num = num.replace("1/2", ".5")
        return num

    @classmethod
    def parse_decimal(cls, num):
        """Fix half glyphs."""
        if isinstance(num, str):
            num = num.strip()
            num = num.replace(" ", "")
            num = num.replace("½", ".5")
            num = num.replace("1/2", ".5")
            nums = cls.DECIMAL_MATCHER.findall(num)
            if nums:
                num = nums[0]
        return Decimal(num)

    @classmethod
    def remove_volume_prefixes(cls, volume):
        """Remove common volume prefixes."""
        lowercase_volume = volume.lower()
        for prefix in cls.VOLUME_PREFIXES:
            if lowercase_volume.startswith(prefix):
                prefix_len = len(prefix)
                volume = volume[prefix_len:].strip()
        return volume

    def _add_credit(self, person, role, primary=None):
        """Add a credit to the metadata."""
        person = person.strip()
        if not person:
            return
        if role is None:
            role = ""
        else:
            role = role.strip()

        credit = {"person": person, "role": role}
        if self.metadata.get("credits"):
            # if we've already added it, return
            for old_credit in self.metadata["credits"]:
                if self._credit_key(old_credit) == self._credit_key(credit):
                    return

        if "credits" not in self.metadata:
            self.metadata["credits"] = []
        if primary is not None:
            credit["primary"] = primary
        self.metadata["credits"].append(credit)

    def _get_cover_page_filenames_tagged(self):
        """Overridden by CIX."""
        return frozenset()

    def get_num_pages(self):
        """Get the number of pages."""
        if self._page_filenames is not None:
            return len(self._page_filenames)

    def set_page_metadata(self, archive_filenames):
        """Parse the filenames that are comic pages."""
        self._page_filenames = []
        for filename in archive_filenames:
            if IMAGE_EXT_RE.search(filename) is not None:
                self._page_filenames.append(filename)
        self.metadata["page_count"] = len(self._page_filenames)
        self.metadata["cover_image"] = self.get_cover_page_filename()

    def get_pagename(self, index):
        """Get the filename of the page by index."""
        if self._page_filenames:
            return self._page_filenames[index]

    def get_cover_page_filename(self):
        """Get filename of most likely coverpage."""
        cover_image = None
        coverlist = self._get_cover_page_filenames_tagged()
        if coverlist:
            cover_image = sorted(coverlist)[0]
        if not cover_image:
            cover_image = self.metadata.get("cover_image")
        if not cover_image and self._page_filenames:
            cover_image = self._page_filenames[0]
        return cover_image

    def get_pagenames_from(self, index_from):
        """Return a list of page filenames from the given index onward."""
        if self._page_filenames:
            return self._page_filenames[index_from:]

    def synthesize_metadata(self, md_list):
        """Overlay the metadatas in precedence order."""
        all_credits_map = {}
        all_tags = {}
        for md in md_list:
            # pop off complex values before simple update
            # "pages" is complex but only comes from cix so no synth needed.

            # Synthesize credits
            try:
                credits = md.pop("credits")
                for credit in credits:
                    credit_key = self._credit_key(credit)
                    if credit_key not in all_credits_map:
                        all_credits_map[credit_key] = {}
                    all_credits_map[credit_key].update(credit)
            except KeyError:
                pass
            except Exception as exc:
                LOG.warning(f"{self.path} error combining credits: {exc}")

            # Synthesize tags
            for tag in self.STR_SET_TAGS:
                # synthesize sets of attributes
                try:
                    tags = md.pop("tag")
                    if tags:
                        if tag not in all_tags:
                            all_tags[tag] = set()
                        all_tags[tag].update(tags)
                except KeyError:
                    pass
                except Exception as exc:
                    LOG.warning(f"{self.path} error combining {tag}: {exc}")

            self.metadata.update(md)
        final_credits = list(all_credits_map.values())
        if final_credits:
            self.metadata["credits"] = final_credits
        self.metadata.update(all_tags)

    def from_string(self, _):
        """Stub method."""
        raise NotImplementedError()

    def from_file(self, _):
        """Stub method."""
        raise NotImplementedError()
