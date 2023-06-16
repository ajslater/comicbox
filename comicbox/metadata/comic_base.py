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
            if val == cls.LTR:
                return cls.LTR
            return None

    STR_SET_TAGS = frozenset(
        (
            "characters",
            "locations",
            "tags",
            "teams",
            "genres",
            "series_groups",
        )
    )
    STR_LIST_RE = re.compile(r"[,;]")
    BOOL_TAGS = frozenset(("black_and_white",))
    DICT_LIST_TAGS = frozenset(("credits", "pages"))
    CSV_DICT_LIST_MAP = {"story_arcs": "story_arc_number"}
    DICT_TAGS = frozenset(("story_arcs",))
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
    TRUTHY_VALUES = frozenset(("yes", "true", "1"))
    DECIMAL_MATCHER = re.compile(r"\d*\.?\d+")
    CREDIT_TAGS = {
        "colorist": frozenset(["colorist", "colourist", "colorer", "colourer"]),
        "cover": frozenset(
            ["cover", "covers", "coverartist", "cover artist", "coverDesigner"]
        ),
        "editor": frozenset(["editor"]),
        "inker": frozenset(["inker", "artist", "finishes"]),
        "letterer": frozenset(["letterer"]),
        "penciller": frozenset(["artist", "penciller", "penciler", "breakdowns"]),
        "writer": frozenset(["writer", "author", "plotter", "scripter", "creator"]),
    }
    KEY_MAP = {}

    def __init__(  # noqa: PLR0913
        self,
        path=None,
        string=None,
        metadata_path=None,
        native_dict=None,
        metadata=None,
    ):
        """Initialize the metadata dict or parse it from a source."""
        self.metadata = {}
        self._page_filenames = None
        self.path = path
        if metadata is not None:
            self.metadata = metadata
        if native_dict is not None:
            self.from_dict(native_dict)
        if string is not None:
            self.from_string(string)
        if metadata_path is not None:
            self.from_file(metadata_path)

    @classmethod
    def is_truthy(cls, value):
        """Return if value is truthy."""
        try:
            if isinstance(value, str) and value.lower() in cls.TRUTHY_VALUES:
                result = True
            else:
                result = bool(value)
        except Exception:
            result = False
        return result

    @staticmethod
    def _credit_key(credit):
        """Get a unique key for credits."""
        return f"{credit.get('role')}:{credit.get('person')}".lower()

    @staticmethod
    def parse_pycountry(tag, name, long_to_alpha2=True):
        """Convert countries and languages to long names or alpha2."""
        if tag == "country":
            module = pycountry.countries
        elif tag == "language":
            module = pycountry.languages
        else:
            reason = f"no pycountry module for {tag}"
            raise NotImplementedError(reason)
        name = name.strip()
        if not name:
            return None
        if len(name) == 2:  # noqa PLR2004
            # Language lookup fails for 'en' unless alpha_2 is specified.
            obj = module.get(alpha_2=name)
        else:
            obj = module.lookup(name)

        if obj is None:
            reason = f"couldn't find {tag} for {name}"
            raise ValueError(reason)

        if long_to_alpha2:
            return obj.alpha_2
        return obj.name

    @classmethod
    def normalize_key(cls, parser_classes, key):
        """Normalize a single key with parsers."""
        comicbox_key = key
        for parser in parser_classes:
            if native_key := parser.KEY_MAP.get(key):
                comicbox_key = native_key
                break
        return comicbox_key

    @classmethod
    def normalize_metadata(cls, parser_classes, md):
        """Normalize metadata to comicbox format with parsers."""
        normal_md = {}
        for key, value in md:
            comicbox_key = cls.normalize_key(parser_classes, key)
            normal_md[comicbox_key] = value
        return normal_md

    @classmethod
    def parse_bool(cls, value):
        """Parse boolean type."""
        return cls.is_truthy(value)

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
    def parse_str_set(cls, list_str):
        """Parse a string list into a set."""
        str_stripped_list = cls.parse_str_list(list_str)
        return frozenset(str_stripped_list)

    @classmethod
    def parse_int(cls, value):
        """Parse an integer value."""
        return int(value)

    @classmethod
    def parse_str_list(cls, list_str):
        """Parse a list of delimited strings."""
        str_list = cls.STR_LIST_RE.split(list_str)
        str_stripped_list = []
        for item in str_list:
            if stripped_item := item.strip():
                str_stripped_list.append(stripped_item)
        return str_stripped_list

    @classmethod
    def parse_int_list(cls, value):
        """Parse a list of ints."""
        return [int(x) for x in value.split(",")]

    @classmethod
    def remove_volume_prefixes(cls, volume):
        """Remove common volume prefixes."""
        lowercase_volume = volume.lower()
        for prefix in cls.VOLUME_PREFIXES:
            if lowercase_volume.startswith(prefix):
                prefix_len = len(prefix)
                volume = volume[prefix_len:].strip()
        return volume

    def __eq__(self, obj):
        """== operator."""
        return bool(DeepDiff(self.metadata, obj.metadata, ignore_order=True))

    def _add_credit(self, person, role, primary=None):
        """Add a credit to the metadata."""
        person = person.strip()
        if not person:
            return
        role = "" if role is None else role.strip()

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
        return None

    def set_page_metadata(self, archive_filenames, is_pdf=False):
        """Parse the filenames that are comic pages."""
        if is_pdf:
            self._page_filenames = archive_filenames
        else:
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
        return None

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

    def get_pagenames_from(self, index_from=None, index_to=None):
        """Return a list of page filenames from the given index onward."""
        if self._page_filenames:
            if index_from is None:
                index_from = 0
            if index_to is None:
                index_to = -1
            elif index_to > 0:
                index_to += 1
            return self._page_filenames[index_from:index_to]
        return None

    def _synth_md_tag(self, md, all_credits_map, all_tags):
        """Pop off complex values before simple update.

        "pages" is complex but only comes from cix so no synth needed.
        """
        # Synthesize credits
        try:
            md_credits = md.pop("credits")
            for credit in md_credits:
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

    def synthesize_metadata(self, md_list):
        """Overlay the metadatas in precedence order."""
        all_credits_map = {}
        all_tags = {}
        for md in md_list:
            self._synth_md_tag(md, all_credits_map, all_tags)
        final_credits = list(all_credits_map.values())
        if final_credits:
            self.metadata["credits"] = final_credits
        self.metadata.update(all_tags)

    def from_dict(self, metadata):
        """Noop method."""
        return metadata

    def from_string(self, _):
        """Stub method."""
        raise NotImplementedError

    def from_file(self, _):
        """Stub method."""
        raise NotImplementedError

    def to_dict(self):
        """Noop method."""
        return self.metadata

    def to_string(self):
        """Stub method."""
        raise NotImplementedError

    def to_file(self, _):
        """Stub method."""
        raise NotImplementedError

    @staticmethod
    def is_number_or_truthy(value):
        """See if value is a throwaway."""
        return value in (False, 0) or value

    @staticmethod
    def serialize_str_set(value):
        """Serialize string set tags."""
        return ",".join(sorted(value))

    @staticmethod
    def serialize_bool(value):
        """Serialize bool tags."""
        return str(value).lower()

    @classmethod
    def serialize_pycountry(cls, tag, value):
        """Serialize a pycountry tag."""
        return cls.parse_pycountry(tag, value, False)

    @staticmethod
    def serialize_decimal(value):
        """Serialize a decimal tag."""
        return str(value)

    @staticmethod
    def serialize_issue(value):
        """Serialize issue tags."""
        return str(value)

    @staticmethod
    def serialize_int(value):
        """Serialize int tags."""
        return str(value)
