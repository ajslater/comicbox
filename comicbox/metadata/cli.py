"""Metadata cli format."""
from pathlib import Path
from typing import Optional

from comicbox.metadata.comet import CoMet
from comicbox.metadata.comic_base import ComicBaseMetadata
from comicbox.metadata.comicbookinfo import ComicBookInfo
from comicbox.metadata.comicinfoxml import ComicInfoXml
from comicbox.metadata.pdf import PDFParser


class CLIMetadata(ComicBaseMetadata):
    """CLI format."""

    PARSER_CLASSES = (ComicInfoXml, ComicBookInfo, CoMet, PDFParser)
    FILENAME = "comicbox-cli.txt"
    CONFIG_KEYS = frozenset(("cli",))

    def parse_story_arcs(self, story_arc_str):
        """Parse story arcs like a:1,b:2."""
        arc_strs = self.parse_str_list(story_arc_str)
        story_arcs = {}
        for arc in arc_strs:
            parts = arc.split(":")
            name = parts[0]
            number = self.parse_int(parts[1]) if len(parts) > 1 else None
            story_arcs[name] = number
        return story_arcs

    def parse_credits(self, credits_str):
        """Parse credits like role:person,role:parson."""
        credit_strs = self.parse_str_list(credits_str)
        credit_list = []
        for credit_str in credit_strs:
            role, person = credit_str.split(":")
            credit_dict = {role: person}
            credit_list.append(credit_dict)
        return credit_list

    def parse_pages(self, pages_list_str):
        """Parse metadata pages tag."""
        # XXX Only does three attributes.
        pages_strs = pages_list_str.split(",")
        pages = []
        for page_str in pages_strs:
            page_array = page_str.split(":")
            if not page_array:
                continue
            page = {"image": page_array[0]}
            if len(page_array) > 1:
                page["image_size"] = int(page_array[1])
            if len(page_array) > 2:  # noqa PLR2004
                page_type = page_array[2]
                if page_type in ComicInfoXml.PageInfo.PageType.ALL:
                    page["type"] = page_type
            pages.append(page)
        return pages

    def parse_value(self, key, unparsed_value):
        """Parse a key value pair."""
        if key in self.BOOL_TAGS:
            value = self.parse_bool(unparsed_value)
        elif key == "credits":
            value = self.parse_credits(unparsed_value)
        elif key in self.DECIMAL_TAGS:
            value = self.parse_decimal(unparsed_value)
        elif key in self.INT_TAGS:
            value = self.parse_int(unparsed_value)
        elif key in self.ISSUE_TAGS:
            value = self.parse_issue(unparsed_value)
        elif key == "pages":
            value = self.parse_pages(unparsed_value)
        elif key in self.PYCOUNTRY_TAGS:
            value = self.parse_pycountry(key, unparsed_value)
        elif key == "story_arcs":
            value = self.parse_story_arcs(unparsed_value)
        elif key in self.STR_SET_TAGS:
            value = self.parse_str_set(unparsed_value)
        else:
            value = str(unparsed_value)
        return value

    def from_string(self, md_string):
        """Parse metadtaa from cli strings."""
        kv_pairs = md_string.split(";")
        for kv_pair in kv_pairs:
            key, values_str = kv_pair.split("=")
            comicbox_key = self.normalize_key(self.PARSER_CLASSES, key)
            parsed_value = self.parse_value(comicbox_key, values_str)
            if parsed_value is not None:
                self.metadata[comicbox_key] = parsed_value

    @staticmethod
    def serialize_dict(value):
        """Serialize dict tag."""
        items = []
        for name, number in value.items:
            item = name
            if number is not None:
                item += f":{number}"
            items.append(item)
        if not items:
            return None
        return ",".join(items)

    @staticmethod
    def serialize_credits(credit_list):
        """Serialize credits tag."""
        items = []
        for role, person in credit_list:
            item = role + ":" + person
            items.append(item)
        if not items:
            return None
        return ",".join(items)

    @staticmethod
    def serialize_pages(pages):
        """Serialize pages tag."""
        # XXX Only does three attributes.
        if not pages:
            return None
        page_strs = []
        for page in pages:
            page_array = []
            if image := page.get("image"):
                page_array.append(image)
                if image_size := page.get("image_size"):
                    page_array.append(image_size)
                    if page_type := page.get("type"):
                        page_array.append(page_type)
            if not page_array:
                continue
            page_str = ":".join(page_array)
            page_strs.append(page_str)
        if not page_strs:
            return None
        return ",".join(page_strs)

    SERIALIZER_MAP = {
        ComicBaseMetadata.STR_SET_TAGS: ComicBaseMetadata.serialize_str_set,
        ComicBaseMetadata.BOOL_TAGS: ComicBaseMetadata.serialize_bool,
        ComicBaseMetadata.DICT_TAGS: serialize_dict,
        frozenset(["credits"]): serialize_credits,
        frozenset(["pages"]): serialize_pages,
        ComicBaseMetadata.DECIMAL_TAGS: ComicBaseMetadata.serialize_decimal,
        ComicBaseMetadata.ISSUE_TAGS: ComicBaseMetadata.serialize_issue,
        ComicBaseMetadata.INT_TAGS: ComicBaseMetadata.serialize_int,
    }

    def _to_string_line(self, key, value):
        value_str: Optional[str] = None

        if key in self.PYCOUNTRY_TAGS:
            value_str = self.serialize_pycountry(key, value)
        else:
            serializer = str
            for key_set, method in self.SERIALIZER_MAP.items():
                if key in key_set:
                    serializer = method
                    break
            value_str = serializer(value)

        if not value_str:
            return None
        return "=".join([key, value_str])

    def to_string(self):
        """Serialize metadata as a long string."""
        items = []
        for key, value in self.metadata.items():
            item = self._to_string_line(key, value)
            if item:
                items.append(item)
        return ";".join(sorted(items))

    def from_file(self, path):
        """Parse metadata from a file."""
        path = Path(path)
        with path.open("r") as f:
            for line in f.readline():
                self.from_string(line)

    def to_file(self, path: Path):
        """Serialize metadata to a file."""
        big_line = self.to_string() + "\n"

        with path.open("w") as f:
            f.write(big_line)

    def from_dict(self, metadata):
        """Parse metadata from a dict."""
        for key, value in metadata.items():
            normal_key = self.normalize_key(self.PARSER_CLASSES, key)
            self.metadata[normal_key] = value
