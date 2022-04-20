"""Metadata class for a comic archive."""
import re

from decimal import Decimal
from logging import getLogger

import pycountry


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

    STR_SET_TAGS = set(
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
    BOOL_SET_TAGS = set(("black_and_white",))
    DICT_LIST_TAGS = set(("credits", "pages"))
    PYCOUNTRY_TAGS = set(("country", "language"))
    DECIMAL_TAGS = set(
        (
            "community_rating",
            "critical_rating",
            "price",
        )
    )
    ISSUE_TAGS = set(("issue", "alternate_issue"))
    INT_TAGS = set(
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
    # _ISSUE_MATCHER = re.compile(r"\d(+.?\d*|)\S*")  # TODO UNUSED

    def __init__(self, string=None, path=None, metadata=None):
        """Initialize the metadata dict or parse it from a source."""
        self.metadata = {}
        self._page_filenames = None
        self.path = path
        if metadata is not None:
            self.metadata = metadata
            return
        elif string is not None:
            self.from_string(string)
            return
        elif path is not None:
            self.from_file(path)
            return

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

    @classmethod
    def _compare_dict_list(cls, list_a, list_b):
        """Compare lists of dicts."""
        if list_a is None and list_b is None:
            return True
        if list_a is None and list_b or list_b is None and list_a:
            return False
        for dict_a in list_a:
            match = False
            for dict_b in list_b:
                if dict_a == dict_b:
                    match = True
                    break
            if not match:
                LOG.debug("dict_compare: could not find:", dict_a)
                return False
        return True

    @classmethod
    def _compare_metadatas(cls, md_a, md_b):
        # TODO remove
        for key, val_a in md_a.items():
            val_b = md_b.get(key)
            if key in cls.IGNORE_COMPARE_TAGS:
                continue
            if key in cls.DICT_LIST_TAGS:
                res = cls._compare_dict_list(val_a, val_b)
                if not res:
                    LOG.debug(f"compare metatada: {key} {val_a} != {val_b}")
                    print(f"compare metatada: {key} {val_a} != {val_b}")
                    return False
            else:
                if val_a != val_b:
                    LOG.debug(f"compare metatada: {key} {val_a} != {val_b}")
                    print(f"compare metatada: {key} {val_a} != {val_b}")
                    return False
        return True

    def __eq__(self, obj):
        """== operator."""
        return self.metadata == obj.metadata
        # return self._compare_metadatas(
        #    obj.metadata, self.metadata
        # ) and self._compare_metadatas(self.metadata, obj.metadata)

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
        """Remove common volume prefixes"""
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
        if primary is not None:
            credit["primary"] = primary

        if self.metadata.get("credits") is None:
            self.metadata["credits"] = []

        # if we've already added it, return
        for old_credit in self.metadata["credits"]:
            if self._credit_key(old_credit) == self._credit_key(credit):
                return

        self.metadata["credits"].append(credit)

    def _get_cover_page_filenames_tagged(self):
        """Overriden by CIX."""
        return set()

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

        if not cover_image:
            LOG.warning(f"{self.path} could not find cover filename")
        return cover_image

    def get_pagenames_from(self, index_from):
        """Return a list of page filenames from the given index onward."""
        if self._page_filenames:
            return self._page_filenames[index_from:]

    def synthesize_metadata(self, md_list):
        """Overlay the metadatas in precedence order."""
        final_credits = {}
        all_tags = {}
        for md in md_list:
            # pop off complex values before simple update
            # "pages" is complex but only comes from cix so no synth needed.

            # Synthesize credits
            try:
                credits = md.pop("credits")
                for credit in credits:
                    credit_key = self._credit_key(credit)
                    if credit_key not in final_credits:
                        final_credits[credit_key] = {}
                    final_credits[credit_key].update(credit)
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
                    LOG.warning(f"{self.path} error comibining {tag}: {exc}")

            self.metadata.update(md)
        self.metadata["credits"] = list(final_credits.values())
        self.metadata.update(all_tags)

    def from_string(self, _):
        """Stub method."""
        raise NotImplementedError()

    def from_file(self, _):
        """Stub method."""
        raise NotImplementedError()

    # SCHEMA = {
    #    # CIX, CBI AND COMET
    #    "genre": str,
    #    "issue": str,
    #    "credits": [{"name": str, "role": str}],
    #    "language": str,  # two letter iso code
    #    "publisher": str,
    #    "series": str,
    #    "title": str,
    #    "volume": int,
    #    "year": int,
    #    "month": int,
    #    "day": int,
    #    # CIX AND CBI ONLY
    #    "comments": str,
    #    "issue_count": int,
    #    # CIX AND COMET ONLY
    #    "characters": set,
    #    "reading_direction": ReadingDirection,
    #    "age_rating": str,
    #    "format": str,
    #    # CBI AND COMET ONLY
    #    "critical_rating": int, -> dec
    #    # CIX ONLY
    #    "alternate_issue": str,
    #    "alternate_issue_count": int,
    #    "alternate_series": str,
    #    "black_and_white": bool,
    #    "community_rating": dec
    #    "imprint": str,
    #    "locations": set,
    #    "manga": bool,
    #    "notes": str,
    #    "pages": [{"page": int, "type": "PageType"}],
    #    "scan_info": str,
    #    "series_group": str,
    #    "story_arc": str,
    #    "teams": set,
    #    "web": str,
    #    # CBI_ONLY
    #    "country": str,
    #    "volume_count": int,
    #    "tags": set,
    #    # COMET_ONLY
    #    "cover_image": str,
    #    "description": str,
    #    "identifier": str,
    #    "last_mark": int,
    #    "price": float,
    #    "rights": str,
    #    "page_count": int,
    #    "is_version_of": str,
    #    # COMICBOX_ONLY
    #    "ext": str,
    #    "remainder": sr
    # }
    # SPECIAL_TAGS = (
    #    "credits",
    #    "language",
    #    "country",
    #    "date",
    #    "pages",
    #    "reading_direction",
    #    "manga",
    # )
    # BOOL_TAGS = ("black_and_white", "manga")
