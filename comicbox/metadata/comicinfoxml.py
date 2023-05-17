"""A class to encapsulate ComicRack's ComicInfo.xml data."""
from dataclasses import dataclass
from logging import getLogger
from xml.etree.ElementTree import Element, ElementTree, SubElement

from stringcase import pascalcase, snakecase

from comicbox.metadata.comic_xml import ComicXml

LOG = getLogger(__name__)


class ComicInfoXml(ComicXml):
    """Comic Rack Metadata."""

    # Schema from
    # https://anansi-project.github.io/docs/comicinfo/schemas/v2.1

    @dataclass
    class PageInfo:
        """CIX Page Info."""

        class PageType:
            """CIX Page Type Schema."""

            FRONT_COVER = "FrontCover"
            INNER_COVER = "InnerCover"
            ROUNDUP = "Roundup"
            STORY = "Story"
            ADVERTISEMENT = "Advertisement"
            EDITORIAL = "Editorial"
            LETTERS = "Letters"
            PREVIEW = "Preview"
            BACK_COVER = "BackCover"
            OTHER = "Other"
            DELETED = "Deleted"

        image: int
        page_type: str = PageType.STORY
        double_page: bool = False
        image_size: int = 0
        key: str = ""
        bookmark: str = ""
        image_width: int = -1
        image_height: int = -1

    class YesNoTypes:
        """Text Boolean Types."""

        YES = "Yes"
        NO = "No"

    class MangaTypes(YesNoTypes):
        """Manga Types."""

        YES_RTL = "YesAndRightToLeft"
        RTL_VALUES = ("YesRtl".lower(), YES_RTL.lower())

    class AgeRatingTypes:
        """Age Ratings."""

        A_18_PLUS = "Adults Only 18+"
        EARLY_CHILDHOOD = "Early Childhood"
        EVERYONE = "Everyone"
        E_10_PLUS = "Everyone 10+"
        G = "G"
        KIDS_TO_ADULTS = "Kids to Adults"
        M = "M"
        MA_15_PLUS = "MA15+"
        MA_17_PLUS = "Mature 17+"
        PG = "PG"
        R_18_PLUS = "R18+"
        PENDING = "Rating Pending"
        TEEN = "Teen"
        X_18_PLUS = "X18+"

    FILENAME = "comicinfo.xml"
    ROOT_TAG = "ComicInfo"

    # order of tags from:
    # https://anansi-project.github.io/docs/comicinfo/schemas/v2.1
    XML_TAGS = {
        "Title": "title",
        "Series": "series",
        "Number": "issue",
        "Count": "issue_count",
        "Volume": "volume",
        "AlternateSeries": "alternate_series",
        "AlternateNumber": "alternate_issue",
        "AlternateCount": "alternate_issue_count",
        "Summary": "summary",
        "Notes": "notes",
        "Year": "year",
        "Month": "month",
        "Day": "day",
        #
        # Credit tags here handled separately
        #
        "Publisher": "publisher",
        "Imprint": "imprint",
        "Genre": "genres",
        "Tags": "tags",
        "Web": "web",
        # "PageCount": None,  # unused, calculated.
        "LanguageISO": "language",  # two letter in the lang list
        "Format": "format",
        "BlackAndWhite": "black_and_white",
        "Manga": "manga",  # type(MangaType),  # Yes, YesRTL, No
        "Characters": "characters",
        "Teams": "teams",
        "Locations": "locations",
        "ScanInformation": "scan_info",
        # Mylar writes csvs for StoryArc & StoryArcNumber for multiple story arcs.
        "StoryArc": "story_arcs",
        "StoryArcNumber": "story_arc_number",
        "SeriesGroup": "series_groups",
        "AgeRating": "age_rating",
        # "Pages": None,  # unused, unparsed
        "CommunityRating": "community_rating",
        # "MainCharacterOrTeam": None,  # unused
        "Review": "review",
        "GTIN": "gtin",
    }

    def _from_xml_credits(self, root):
        for role in self.CREDIT_TAGS:
            for element in root.findall(role):
                if not element.text:
                    continue
                for name in element.text.split(","):
                    self._add_credit(name, role)

    def _from_xml_manga(self, _, val):
        """Accept CIX 2.0 Manga Types and old truthy values."""
        val = val.lower()
        if val in self.MangaTypes.RTL_VALUES:
            self.metadata["reading_direction"] = self.ReadingDirection.RTL
            return True
        return val in self.TRUTHY_VALUES

    def _from_xml_tag(self, to_tag, val):  # noqa C901
        """Parse one xml tag."""
        if to_tag in self.ISSUE_TAGS:
            val = self.parse_issue(val)
        elif to_tag in self.INT_TAGS:
            if to_tag == "volume":
                val = self.remove_volume_prefixes(val)
            val = int(val)
        elif to_tag in self.DECIMAL_TAGS:
            val = self.parse_decimal(val)
        elif to_tag in self.STR_SET_TAGS:
            val = frozenset([item.strip() for item in val.split(",")])
            if len(val) == 0:
                return
        # special bool tags
        elif to_tag in self.BOOL_SET_TAGS:
            val = self.parse_bool(val)
        elif to_tag == "manga":
            val = self._from_xml_manga(to_tag, val)
        elif to_tag in self.PYCOUNTRY_TAGS:
            val = self._pycountry(to_tag, val)
            if not val:
                return
        elif to_tag in self.CSV_DICT_LIST_MAP:
            val = val.split(",")
        elif to_tag in self.CSV_DICT_LIST_MAP.values():
            val = [int(x) for x in val.split(",")]
        self.metadata[to_tag] = val

    def _map_dicts(self):
        for key_key, value_key in self.CSV_DICT_LIST_MAP.items():
            key_list = self.metadata.pop(key_key, None)
            if not key_list:
                continue
            value_list = self.metadata.pop(value_key, [])
            diff = max(len(key_list) - len(value_list), 0)
            value_list += [None] * diff
            self.metadata[key_key] = dict(zip(key_list, value_list, strict=True))

    def _from_xml_tags(self, root):
        for from_tag, to_tag in self.XML_TAGS.items():
            try:
                element = root.find(from_tag)
                if element is None or element.text is None:
                    continue
                val = str(element.text).strip()
                if not val:
                    continue
                self._from_xml_tag(to_tag, val)
            except Exception as exc:
                LOG.warning(f"{self.path} CIX {from_tag} {exc}")
        self._map_dicts()

    def _from_xml_pages(self, root):
        pages = root.find("Pages")
        if pages is not None:
            self.metadata["pages"] = []
            for page in pages.findall("Page"):
                snake_dict = {}
                for key, value in page.attrib.items():
                    snake_dict[snakecase(key)] = value
                self.metadata["pages"].append(snake_dict)

    def _from_xml(self, tree):
        root = self._get_xml_root(tree)
        self._from_xml_tags(root)
        self._from_xml_credits(root)
        self._from_xml_pages(root)

    def _to_xml_root(self):
        root = Element(self.ROOT_TAG)
        root.attrib["xmlns:xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
        root.attrib["xmlns:xsd"] = "http://www.w3.org/2001/XMLSchema"
        return root

    def _to_xml_tags_yes_no(self, val):
        return self.YesNoTypes.YES if val else self.YesNoTypes.NO

    def _to_xml_manga(self, val):
        if val:
            if self.metadata["reading_direction"] == self.ReadingDirection.RTL:
                return self.MangaTypes.YES_RTL
            return self.MangaTypes.YES
        return self.MangaTypes.NO

    def _to_xml_csv_map(self, root, val, key_tag, value_tag):
        sorted_arcs = dict(sorted(val.items()))
        keys_val = ",".join(sorted_arcs.keys())
        SubElement(root, key_tag).text = keys_val
        values_val = ",".join(str(x) for x in sorted_arcs.values())
        SubElement(root, value_tag).text = values_val

    def _to_xml_tags(self, root):
        """Write tags to xml."""
        for xml_tag, md_key in self.XML_TAGS.items():
            val = self.metadata.get(md_key)
            if val:
                if xml_tag == "BlackAndWhite":
                    new_val = self._to_xml_tags_yes_no(val)
                elif xml_tag == "Manga":
                    new_val = self._to_xml_manga(val)
                elif xml_tag == "StoryArc":
                    self._to_xml_csv_map(root, val, "StoryArc", "StoryArcNumber")
                    continue
                new_val = ",".join(sorted(val)) if md_key in self.STR_SET_TAGS else val
                SubElement(root, xml_tag).text = str(new_val)

    def _to_xml_pages(self, root):
        md_pages = self.metadata.get("pages")
        if md_pages:
            page_count = len(self.metadata["pages"])
            if page_count:
                pages = SubElement(root, "Pages")
                for page in self.metadata["pages"]:
                    pascal_dict = {}
                    for key, value in page.items():
                        pascal_dict[pascalcase(key)] = value
                    SubElement(pages, "Page", attrib=pascal_dict)
        else:
            page_count = self.get_num_pages()
        SubElement(root, "PageCount").text = str(page_count)

    def _to_xml_credits(self, root):
        consolidated_credits = {}
        # Extract credits and consolidate
        for credit in self.metadata["credits"]:
            for key, synonyms in self.CREDIT_TAGS.items():
                if credit["role"].lower() in synonyms:
                    cleaned_person = credit["person"].replace(",", "").strip()
                    if not cleaned_person:
                        continue
                    if key not in consolidated_credits:
                        consolidated_credits[key] = set()
                    consolidated_credits[key].add(cleaned_person)
        # write the consolidated tags to xml
        for tag, people in consolidated_credits.items():
            SubElement(root, tag).text = ", ".join(sorted(people))

    def _to_xml(self):
        """Translate comicbox metadata into a comicinfo xml tree."""
        root = self._to_xml_root()
        self._to_xml_tags(root)
        self._to_xml_pages(root)
        self._to_xml_credits(root)
        return ElementTree(root)

    def _get_cover_page_filenames_tagged(self):
        coverlist = set()
        for page in self.metadata.get("pages", []):
            if page.get("type") == self.PageInfo.PageType.FRONT_COVER:
                index = page.get("image")
                num_pages = self.get_num_pages()
                if (
                    self._page_filenames
                    and num_pages is not None
                    and index <= num_pages
                ):
                    coverlist.add(self._page_filenames[index])
        return frozenset(coverlist)

    def compute_pages_tags(self, infolist):
        """Recompute the page tags with actual image sizes."""
        new_pages = []
        index = 0
        old_pages = self.metadata.get("pages")
        front_cover_set = False
        for index, info in enumerate(infolist):
            new_page = {"image": str(index), "image_size": str(info.file_size)}
            if (
                old_pages
                and len(old_pages) > index
                and old_pages[index].get("type") == self.PageInfo.PageType.FRONT_COVER
            ):
                new_page["type"] = self.PageInfo.PageType.FRONT_COVER
                front_cover_set = True
            # new_page["image_width"] = pillow
            # new_page["image_height"] = pillow
            new_pages.append(new_page)
        if not front_cover_set and len(new_pages) > 0:
            new_pages[0]["type"] = self.PageInfo.PageType.FRONT_COVER
        self.metadata["pages"] = new_pages
