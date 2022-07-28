"""A class to encapsulate ComicRack's ComicInfo.xml data."""
from logging import getLogger
from xml.etree.ElementTree import Element, ElementTree, SubElement

from comicbox.metadata.comic_xml import ComicXml


LOG = getLogger(__name__)


class ComicInfoXml(ComicXml):
    """Comic Rack Metadata."""

    # Schema from
    # https://github.com/anansi-project/comicinfo/blob/main/schema/v2.0/ComicInfo.xsd

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
    # https://github.com/anansi-project/comicinfo/blob/main/schema/v2.0/ComicInfo.xsd
    XML_TAGS = {
        "Title": "title",
        "Series": "series",
        "Number": "issue",
        "Count": "issue_count",
        "Volume": "volume",
        "AlternateNumber": "alternate_issue",
        "AlternateCount": "alternate_issue_count",
        "AlternateSeries": "alternate_series",
        "Summary": "summary",
        "Notes": "notes",
        "Year": "year",
        "Month": "month",
        "Day": "day",
        "Publisher": "publisher",
        "Imprint": "imprint",
        "Genre": "genres",
        "Web": "web",
        # PageCount unused
        "LanguageISO": "language",  # two letter in the lang list
        "Format": "format",
        "BlackAndWhite": "black_and_white",
        "Manga": "manga",  # type(MangaType),  # Yes, YesRTL, No
        "Characters": "characters",
        "Teams": "teams",
        "Locations": "locations",
        "ScanInformation": "scan_info",
        "StoryArc": "story_arcs",
        "SeriesGroup": "series_groups",
        "AgeRating": "age_rating",
        # Pages unused
        "CommunityRating": "community_rating",
        # Credits handled speraately
    }

    def _from_xml_credits(self, root):
        for role in self.CREDIT_TAGS.keys():
            for element in root.findall(role):
                if not element.text:
                    continue
                for name in element.text.split(","):
                    self._add_credit(name, role)

    def _from_xml_manga(self, _, val):
        val = val.lower()
        if val in self.MangaTypes.RTL_VALUES:
            self.metadata["reading_direction"] = self.ReadingDirection.RTL
            return True
        return val in self.TRUTHY_VALUES

    def _from_xml_tags(self, root):
        for from_tag, to_tag in self.XML_TAGS.items():
            try:
                element = root.find(from_tag)
                if element is None or element.text is None:
                    continue
                val = str(element.text).strip()
                if not val:
                    continue

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
                        continue
                # special bool tags
                elif to_tag in self.BOOL_SET_TAGS:
                    val = self.parse_bool(val)
                elif to_tag == "manga":
                    val = self._from_xml_manga(to_tag, val)
                elif to_tag in self.PYCOUNTRY_TAGS:
                    val = self._pycountry(to_tag, val)
                    if not val:
                        continue
                self.metadata[to_tag] = val
            except Exception as exc:
                LOG.warning(f"{self.path} CIX {from_tag} {exc}")

    def _from_xml_pages(self, root):
        pages = root.find("Pages")
        if pages is not None:
            self.metadata["pages"] = []
            for page in pages.findall("Page"):
                self.metadata["pages"].append(page.attrib)

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
            else:
                return self.MangaTypes.YES
        else:
            return self.MangaTypes.NO

    def _to_xml_tags(self, root):
        """Write tags to xml."""
        for xml_tag, md_key in self.XML_TAGS.items():
            val = self.metadata.get(md_key)
            if val:
                if xml_tag == "BlackAndWhite":
                    new_val = self._to_xml_tags_yes_no(val)
                if xml_tag == "Manga":
                    new_val = self._to_xml_manga(val)
                if md_key in self.STR_SET_TAGS:
                    new_val = ",".join(sorted(val))
                else:
                    new_val = val
                SubElement(root, xml_tag).text = str(new_val)

    def _to_xml_pages(self, root):
        md_pages = self.metadata.get("pages")
        if md_pages:
            page_count = len(self.metadata["pages"])
            if page_count:
                pages = SubElement(root, "Pages")
                for page in self.metadata["pages"]:
                    SubElement(pages, "Page", attrib=page)
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
        tree = ElementTree(root)
        return tree

    def _get_cover_page_filenames_tagged(self):
        coverlist = set()
        for page in self.metadata.get("pages", []):
            if page.get("Type") == self.PageType.FRONT_COVER:
                index = int(page["Image"])
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
        # Just store this integer data as strings because I don't
        # expect anyone will ever use it.
        new_pages = []
        index = 0
        old_pages = self.metadata.get("pages")
        front_cover_set = False
        for info in infolist:
            if old_pages and len(old_pages) > index:
                new_page = old_pages[index]
                if new_page.get("Type") == self.PageType.FRONT_COVER:
                    front_cover_set = True
            elif info.filename in self._page_filenames:
                new_page = {"Image": str(index)}
            else:
                continue
            new_page["ImageSize"] = str(info.file_size)
            new_pages.append(new_page)
            index += 1
        if not front_cover_set and len(new_pages) > 0:
            new_pages[0]["Type"] = self.PageType.FRONT_COVER
        self.metadata["pages"] = new_pages
