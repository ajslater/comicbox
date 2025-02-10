"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Mapping, Sequence
from enum import Enum
from logging import getLogger
from types import MappingProxyType

from bidict import frozenbidict
from comicfn2dict.parse import comicfn2dict

from comicbox.dict_funcs import deep_update, sort_dict
from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    DEFAULT_NID,
    ISBN_NID,
    NID_ORIGIN_MAP,
    UPC_NID,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    COLORIST_KEY,
    CONTRIBUTORS_KEY,
    COVER_ARTIST_KEY,
    CREATOR_KEY,
    EDITOR_KEY,
    GENRES_KEY,
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    INKER_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LETTERER_KEY,
    LOCATIONS_KEY,
    NAME_KEY,
    NID_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PAGES_KEY,
    PENCILLER_KEY,
    PRICE_KEY,
    PUBLISHER_KEY,
    REPRINT_ISSUE_KEY,
    REPRINT_SERIES_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    SERIES_SORT_NAME_KEY,
    SERIES_START_YEAR_KEY,
    STORIES_KEY,
    STORY_ARCS_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
    WRITER_KEY,
)
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.reprints import reprint_to_filename, sort_reprints
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)

ARCS_TAG = "Arcs"
ARC_NAME_TAG = "Name"
ARC_NUMBER_TAG = "Number"
CHARACTERS_TAG = "Characters"
CREATOR_TAG = "Creator"
CREDITS_TAG = "Credits"
GTIN_TAG = "GTIN"
IMPRINT_TAG = "Imprint"
IDS_TAG = "IDS"
ID_TAG = "ID"
ID_ATTRIBUTE = "@id"
ISBN_TAG = "ISBN"
UPC_TAG = "UPC"
GENRES_TAG = "Genres"
LOCATIONS_TAG = "Locations"
NAME_TAG = "Name"
PRICES_TAG = "Prices"
PRIMARY_ATTRIBUTE = "@primary"
PUBLISHER_TAG = "Publisher"
REPRINTS_TAG = "Reprints"
ROLES_TAG = "Roles"
SERIES_TAG = "Series"
SERIES_ALTERNATIVE_NAMES_TAG = "AlternativeNames"
SERIES_ALTERNATIVE_NAME_TAG = "AlternativeName"
SERIES_FORMAT_TAG = "Format"
SERIES_ISSUE_COUNT_TAG = "IssueCount"
SERIES_LANG_ATTRIBUTE = "@lang"
SERIES_NAME_TAG = "Name"
SERIES_SORT_NAME_TAG = "SortName"
SERIES_START_YEAR_TAG = "StartYear"
SERIES_VOLUME_TAG = "Volume"
SERIES_VOLUME_COUNT_TAG = "VolumeCount"
SOURCE_ATTRIBUTE = "@source"
STORIES_TAG = "Stories"
TEAMS_TAG = "Teams"
TAGS_TAG = "Tags"
URLS_TAG = "URLs"
URL_TAG = "URL"

# Roles
WRITER_TAG = "Writer"
COVER_TAG = "Cover"
COLORIST_TAG = "Colorist"
EDITOR_TAG = "Editor"
INKER_TAG = "Inker"
LETTERER_TAG = "Letterer"
PENCILLER_TAG = "Penciller"

_HOISTABLE_METRON_RESOURCE_TAGS = MappingProxyType(
    {
        (CHARACTERS_TAG, None): CHARACTERS_KEY,
        (GENRES_TAG, None): GENRES_KEY,
        (IDS_TAG, ID_TAG): IDENTIFIERS_KEY,
        (LOCATIONS_TAG, None): LOCATIONS_KEY,
        (PRICES_TAG, None): PRICE_KEY,
        (STORIES_TAG, "Story"): STORIES_KEY,
        (TEAMS_TAG, None): TEAMS_KEY,
        (TAGS_TAG, None): TAGS_KEY,
        (URLS_TAG, None): URL_KEY,
    }
)

_GTIN_NIDS = frozenset({ISBN_NID, UPC_NID})


def _copy_assign(key, data, value):
    if not value:
        return data
    data[key] = value
    return data


class MetronInfoTransform(ComicInfoPagesTransformMixin, IdentifiersTransformMixin):
    """MetronInfo.xml Schema."""

    TRANSFORM_MAP = frozenbidict(
        {
            "AgeRating": "age_rating",
            "BlackAndWhite": "monochrome",
            "CollectionTitle": "series_groups",
            "CoverDate": "date",
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,
            "Pages": PAGES_KEY,
            "Summary": "summary",
            # "URL": WEB_KEY, code
        }
    )
    CONTRIBUTOR_COMICBOX_MAP = MappingProxyType(
        {
            WRITER_TAG: WRITER_KEY,
            "Script": WRITER_KEY,
            "Story": WRITER_KEY,
            "Plot": WRITER_KEY,
            "Interviewer": WRITER_KEY,
            "Artist": PENCILLER_KEY,
            PENCILLER_TAG: PENCILLER_KEY,
            "Breakdowns": PENCILLER_KEY,
            "Illustrator": PENCILLER_KEY,
            "Layouts": PENCILLER_KEY,
            INKER_TAG: INKER_KEY,
            "Embellisher": INKER_KEY,
            "Finishes": INKER_KEY,
            "Ink Assists": INKER_KEY,
            COLORIST_TAG: COLORIST_KEY,
            "Color Separations": COLORIST_KEY,
            "Color Assists": COLORIST_KEY,
            "Color Flats": COLORIST_KEY,
            "Digital Art Technician": CREATOR_KEY,
            "Gray Tone": COLORIST_KEY,
            LETTERER_TAG: LETTERER_KEY,
            COVER_TAG: COVER_ARTIST_KEY,
            EDITOR_TAG: EDITOR_KEY,
            "Consulting Editor": EDITOR_KEY,
            "Assistant Editor": EDITOR_KEY,
            "Associate Editor": EDITOR_KEY,
            "Group Editor": EDITOR_KEY,
            "Senior Editor": EDITOR_KEY,
            "Managing Editor": EDITOR_KEY,
            "Collection Editor": EDITOR_KEY,
            "Production": EDITOR_KEY,
            "Designer": CREATOR_KEY,
            "Logo Design": CREATOR_KEY,
            "Translator": WRITER_KEY,
            "Supervising Editor": EDITOR_KEY,
            "Executive Editor": EDITOR_KEY,
            "Editor In Chief": EDITOR_KEY,
            "President": EDITOR_KEY,
            "Publisher": EDITOR_KEY,
            "Chief Creative Officer": EDITOR_KEY,
            "Executive Producer": EDITOR_KEY,
            "Other": CREATOR_KEY,
        }
    )
    CONTRIBUTOR_SCHEMA_MAP = MappingProxyType(
        {
            COLORIST_KEY: COLORIST_TAG,
            COVER_ARTIST_KEY: COVER_TAG,
            EDITOR_KEY: EDITOR_TAG,
            INKER_KEY: INKER_TAG,
            LETTERER_KEY: LETTERER_TAG,
            PENCILLER_KEY: PENCILLER_TAG,
            WRITER_KEY: WRITER_TAG,
        }
    )
    SERIES_TAG_MAP = frozenbidict(
        {
            SERIES_NAME_TAG: NAME_KEY,
            SERIES_SORT_NAME_TAG: SERIES_SORT_NAME_KEY,
            SERIES_START_YEAR_TAG: SERIES_START_YEAR_KEY,
            SERIES_VOLUME_COUNT_TAG: VOLUME_COUNT_KEY,
        }
    )
    SERIES_VOLUME_TAG_MAP = frozenbidict(
        {
            SERIES_VOLUME_TAG: VOLUME_NUMBER_KEY,
            SERIES_ISSUE_COUNT_TAG: VOLUME_ISSUE_COUNT_KEY,
        }
    )
    GTIN_SUBTAGS = frozenbidict({ISBN_TAG: ISBN_NID, UPC_TAG: UPC_NID})
    SCHEMA_CLASS = MetronInfoSchema
    IDENTIFIERS_TAG = IDS_TAG
    IDENTIFIERS_SUB_TAG = ID_TAG
    URLS_TAG = URLS_TAG
    URLS_SUB_TAG = URL_TAG

    def hoist_metron_resource_lists(self, data):
        """Hoist metron resources into comicbox tags."""
        update_dict = {}
        for tags, key in _HOISTABLE_METRON_RESOURCE_TAGS.items():
            # ignores id tag
            tag, single_tag = tags
            resources = self.hoist_tag(tag, data, single_tag=single_tag)
            if not resources:
                continue
            names = set()
            if isinstance(resources, Sequence | set | frozenset) and not isinstance(
                resources, str
            ):
                for resource in resources:
                    name = get_cdata(resource)
                    if name:
                        names.add(name)
            else:
                names.add(resources)
            if names:
                update_dict[key] = sorted(names)
        if update_dict:
            data.update(update_dict)
        return data

    def lower_metron_resource_lists(self, data):
        """Lower comicbox tags into metron resource tags."""
        update_dict = {}
        for tags, key in _HOISTABLE_METRON_RESOURCE_TAGS.items():
            names = data.pop(key, ())
            if not names:
                continue
            names = sorted(frozenset(names))
            resources = tuple({"#text": name} for name in names if name)
            tag, single_tag = tags
            self.lower_tag(tag, tag, update_dict, resources, single_tag=single_tag)
        if update_dict:
            data.update(update_dict)
        return data

    def _parse_metron_tag_identifier(
        self, data: dict, nss_type: str, nss: str, comicbox_obj: dict
    ):
        """Parse the metron series identifier."""
        nid = data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY, DEFAULT_NID)
        comicbox_identifier = create_identifier(nid, nss, nss_type=nss_type)
        comicbox_obj[IDENTIFIERS_KEY] = {nid: comicbox_identifier}

    def parse_publisher(self, data):
        """Parse Metron Publisher."""
        metron_publisher = data.pop(PUBLISHER_TAG, None)
        if not metron_publisher:
            return data
        publisher = {NAME_KEY: metron_publisher.get(NAME_TAG)}
        if publisher_nss := metron_publisher.get(ID_ATTRIBUTE):
            self._parse_metron_tag_identifier(
                data, "publisher", publisher_nss, publisher
            )
        if publisher:
            data[PUBLISHER_KEY] = publisher
        metron_imprint = metron_publisher.get(IMPRINT_TAG)
        imprint_name = get_cdata(metron_imprint)
        if imprint_name:
            data[IMPRINT_KEY] = imprint_name
        return data

    def _unparse_metron_id_attribute(
        self, data: dict, metron_tag: dict, comicbox_obj: dict
    ):
        """Unparse Metron series identifiers from series identifiers."""
        comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
        if not comicbox_identifiers:
            return
        primary_nid = data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY)
        for nid, identifier in comicbox_identifiers.items():
            if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
                metron_tag[ID_ATTRIBUTE] = nss
                break

    def unparse_publisher(self, data):
        """Unparse Metron publisher."""
        publisher = data.pop(PUBLISHER_KEY, {})
        imprint_name = data.get(IMPRINT_KEY)
        publisher_name = publisher.get(NAME_KEY)
        if not publisher_name and not imprint_name:
            return data
        metron_publisher = {NAME_TAG: publisher_name}
        self._unparse_metron_id_attribute(data, metron_publisher, publisher)
        if imprint_name:
            metron_publisher[IMPRINT_TAG] = {"#text": imprint_name}

        data[PUBLISHER_TAG] = metron_publisher
        return data

    def _hoist_metron_credit(self, metron_credit, contributors):
        """Copy a single emetron style credit dict into contributors."""
        creator = metron_credit.get(CREATOR_TAG, {})
        creator = get_cdata(creator)
        if not creator:
            return
        roles = self.hoist_tag(ROLES_TAG, metron_credit)
        if not roles:
            return
        if isinstance(roles, str):
            roles = (roles,)
        for role in roles:
            metron_role_name = get_cdata(role)
            if not metron_role_name:
                continue
            comicbox_role = self.CONTRIBUTOR_COMICBOX_MAP.get(metron_role_name)
            if not comicbox_role:
                continue
            if comicbox_role not in contributors:
                contributors[comicbox_role] = set()
            contributors[comicbox_role].add(creator)

    def hoist_metron_credits(self, data):
        """Copy metron style credits dict into contributors."""
        metron_credits = self.hoist_tag(CREDITS_TAG, data)
        if not metron_credits:
            return data
        contributors = {}
        if not isinstance(metron_credits, Sequence):
            metron_credits = (metron_credits,)
        for metron_credit in metron_credits:
            self._hoist_metron_credit(metron_credit, contributors)
        return _copy_assign(CONTRIBUTORS_KEY, data, contributors)

    def _aggregate_comicbox_credits_into_metron_credit_dict(self, contributors):
        """Aggregate comicbox credits into Metron credit dict."""
        metron_credit_dict = {}
        for role, names in contributors.items():
            if not role or not names:
                continue
            metron_role = self.CONTRIBUTOR_SCHEMA_MAP.get(role)
            if not metron_role:
                continue
            for name in names:
                if name not in metron_credit_dict:
                    metron_credit_dict[name] = set()
                metron_credit_dict[name].add(metron_role)

        return sort_dict(metron_credit_dict)

    def _serialize_metron_credit_dict_to_list(self, data, metron_credit_dict):
        """Serialize Metron credit dict into list."""
        metron_credits = []
        for name, metron_roles in metron_credit_dict.items():
            if not name or not metron_roles:
                continue
            metron_credit = {CREATOR_TAG: {"#text": name}}
            roles_list = [
                {"#text": metron_role} for metron_role in sorted(metron_roles)
            ]
            self.lower_tag(ROLES_TAG, ROLES_TAG, metron_credit, roles_list)
            metron_credits.append(metron_credit)
        self.lower_tag(CREDITS_TAG, CREDITS_TAG, data, metron_credits)

    def lower_metron_credits(self, data):
        """Dump contributors into metron style credits dict."""
        contributors = data.pop(CONTRIBUTORS_KEY, None)
        if not contributors:
            return data
        metron_credit_dict = self._aggregate_comicbox_credits_into_metron_credit_dict(
            contributors
        )
        self._serialize_metron_credit_dict_to_list(data, metron_credit_dict)
        return data

    def map_arcs_to_story_arcs(self, data):
        """Convert metron arcs to story arcs."""
        arcs = self.hoist_tag(ARCS_TAG, data)
        if not arcs:
            return data
        story_arcs = {}
        for arc in arcs:
            name = arc.get(ARC_NAME_TAG)
            if not name:
                continue
            number = arc.get(ARC_NUMBER_TAG)
            story_arcs[name] = number
        return _copy_assign(STORY_ARCS_KEY, data, story_arcs)

    def map_story_arcs_to_arcs(self, data):
        """Convert story arc dict to metron arcs list."""
        story_arcs = data.get(STORY_ARCS_KEY)
        if not story_arcs:
            return data
        arcs = []
        for name, number in story_arcs.items():
            arc = {ARC_NAME_TAG: name}
            if number is not None:
                arc[ARC_NUMBER_TAG] = number
            arcs.append(arc)
        self.lower_tag(ARCS_TAG, ARCS_TAG, data, arcs)
        return data

    def parse_gtin(self, data):
        """Parse complex metron gtin structure into identifiers."""
        complex_gtin = data.get(GTIN_TAG)
        if not complex_gtin:
            return data
        primary = False
        for tag, nid in self.GTIN_SUBTAGS.items():
            if nss := complex_gtin.get(tag):
                identifier = {NSS_KEY: nss}
                self.parse_assign_identifier(data, nid, identifier, primary)
        return data

    def hoist_reprints(self, data):
        """Parse reprint names into reprint structures."""
        metron_reprints = self.hoist_tag(REPRINTS_TAG, data)
        if not metron_reprints:
            return data
        comicbox_reprints = []
        if isinstance(metron_reprints, str):
            metron_reprints = (metron_reprints,)
        for metron_reprint in metron_reprints:
            name = get_cdata(metron_reprint)
            if not name:
                continue
            fn_dict = comicfn2dict(name)
            new_reprint = {}
            series = fn_dict.get(SERIES_KEY)
            if series:
                new_reprint[REPRINT_SERIES_KEY] = {NAME_KEY: series}
            issue = fn_dict.get(ISSUE_KEY)
            if issue is not None:
                new_reprint[REPRINT_ISSUE_KEY] = issue
            if new_reprint:
                comicbox_reprints.append(new_reprint)
        comicbox_reprints += data.get(REPRINTS_KEY, [])
        if comicbox_reprints:
            data[REPRINTS_KEY] = comicbox_reprints
        return data

    def lower_reprints(self, data):
        """Unparse reprint structures into metron reprint names."""
        reprints = data.get(REPRINTS_KEY)
        if not reprints:
            return data
        metron_reprints = []
        for reprint in reprints:
            name = reprint_to_filename(reprint)
            if name:
                metron_reprints.append({"#text": name})
        self.lower_tag(REPRINTS_TAG, REPRINTS_TAG, data, metron_reprints)
        return data

    def _copy_tags(self, from_dict, to_dict, tag_dict):
        for from_key, to_key in tag_dict.items():
            if value := from_dict.get(from_key):
                to_dict[to_key] = value

    def _parse_metron_series_series_key(self, data, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox series key."""
        series = {}

        self._copy_tags(metron_series, series, self.SERIES_TAG_MAP)

        if series_nss := metron_series.get(ID_ATTRIBUTE):
            self._parse_metron_tag_identifier(data, "series", series_nss, series)

        if series:
            update_dict[SERIES_KEY] = series

    def _parse_metron_series_volume_key(self, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox volume key."""
        volume = {}

        self._copy_tags(metron_series, volume, self.SERIES_VOLUME_TAG_MAP)

        if volume:
            update_dict[VOLUME_KEY] = volume

    def _parse_series_alternative_names(self, data, metron_series) -> dict:
        """Parse metron series alternative name tags into reprints."""
        alternative_names = metron_series.get(SERIES_ALTERNATIVE_NAMES_TAG)
        if not alternative_names:
            return data
        alternative_names = alternative_names.get(SERIES_ALTERNATIVE_NAME_TAG)
        if not alternative_names:
            return data
        reprints = []
        aliases = set()

        if isinstance(alternative_names, Mapping):
            # Marshmallow collapses singleton lists unhelpfully.
            alternative_names = [alternative_names]
        for an in alternative_names:
            alternative_name = get_cdata(an)
            if not alternative_name:
                continue
            aliases.add(alternative_name)
            reprint = {SERIES_KEY: {NAME_KEY: alternative_name}}
            # if alternative_name_id := an.get(ID_ATTRIBUTE):
            # to reprint identifier or main identifier?
            if alternative_name_lang := an.get(SERIES_LANG_ATTRIBUTE):
                reprint[LANGUAGE_KEY] = alternative_name_lang
            reprints.append(reprint)

        reprints += data.get(REPRINTS_KEY, [])
        if reprints:
            data[REPRINTS_KEY] = reprints
        return data

    def parse_metron_series(self, data):
        """Parse complex metron series into comicbox data."""
        metron_series = data.pop(SERIES_TAG, None)
        if not metron_series:
            return data
        update_dict = {}

        if language := metron_series.get(SERIES_LANG_ATTRIBUTE):
            update_dict[LANGUAGE_KEY] = language
        self._parse_metron_series_series_key(data, metron_series, update_dict)
        self._parse_metron_series_volume_key(metron_series, update_dict)
        if original_format := metron_series.get(SERIES_FORMAT_TAG):
            update_dict[ORIGINAL_FORMAT_KEY] = original_format.value
        data = self._parse_series_alternative_names(data, metron_series)

        if update_dict:
            deep_update(data, update_dict)

        return data

    def _aggregate_reprints(self, reprints, new_reprint):
        """Aggregate new reprint into similar old reprint."""
        new_series = new_reprint.get(SERIES_KEY, {})
        new_series_name = new_series.get(NAME_KEY)
        new_lang = new_reprint.get(LANGUAGE_KEY)

        for old_reprint in reprints:
            old_series = old_reprint.get(SERIES_KEY, {})
            old_series_name = old_series.get(NAME_KEY)
            old_lang = old_reprint.get(LANGUAGE_KEY)

            if new_series_name == old_series_name and (
                not new_lang or not old_lang or new_lang == old_lang
            ):
                deep_update(old_reprint, new_reprint)
                break
        else:
            reprints.append(new_reprint)

    def consolidate_reprints(self, data):
        """Consolidate reprints after parsing from series & reprints."""
        old_reprints = data.get(REPRINTS_KEY)
        if not old_reprints:
            return data
        consolidated_reprints = []
        for reprint in old_reprints:
            self._aggregate_reprints(consolidated_reprints, reprint)
        if consolidated_reprints:
            data[REPRINTS_KEY] = sort_reprints(consolidated_reprints)
        return data

    def _unparse_metron_series_alternative_names(self, data, metron_series):
        """Unparse metron series alternative names from reprints."""
        alt_names: list[dict[str, str]] = []
        if reprints := data.get(REPRINTS_KEY):
            for reprint in reprints:
                if series := reprint.get(SERIES_KEY):
                    alt_name: dict[str, str] = {}
                    if series_name := series.get(NAME_KEY):
                        alt_name["#text"] = series_name
                    if series_lang := reprint.get(LANGUAGE_KEY):
                        alt_name[SERIES_LANG_ATTRIBUTE] = series_lang
                    if alt_name:
                        alt_names.append(alt_name)
        if alt_names:
            sorted_alt_names = sorted(alt_names, key=lambda a: ":".join(a.values()))
            metron_series[SERIES_ALTERNATIVE_NAMES_TAG] = {
                SERIES_ALTERNATIVE_NAME_TAG: sorted_alt_names
            }

    def unparse_metron_series(self, data):
        """Unparse the data into the complex metron series tag."""
        metron_series = {}
        if language := data.get(LANGUAGE_KEY):
            metron_series[SERIES_LANG_ATTRIBUTE] = language

        if series := data.get(SERIES_KEY):
            self._copy_tags(series, metron_series, self.SERIES_TAG_MAP.inverse)
            self._unparse_metron_id_attribute(data, metron_series, series)

        if volume := data.get(VOLUME_KEY):
            self._copy_tags(volume, metron_series, self.SERIES_VOLUME_TAG_MAP.inverse)

        if original_format := data.get(ORIGINAL_FORMAT_KEY):
            metron_series[SERIES_FORMAT_TAG] = original_format

        # Add series id
        self._unparse_metron_series_alternative_names(data, metron_series)

        if metron_series:
            if SERIES_TAG not in data:
                data[SERIES_TAG] = {}
            deep_update(data[SERIES_TAG], metron_series)

        return data

    @staticmethod
    def parse_item_primary(item) -> bool:
        """Parse primary attribute."""
        return bool(item.get(PRIMARY_ATTRIBUTE)) if isinstance(item, Mapping) else False

    def parse_identifier(self, item) -> tuple[str, str, str]:
        """Parse identifier dict."""
        source = item.get(SOURCE_ATTRIBUTE)
        if isinstance(source, Enum):
            source = source.value
        nid = NID_ORIGIN_MAP.inverse.get(source, "")
        # These are issues by default.
        nss_type = ""
        nss = get_cdata(item) or "" if nid else ""
        return nid, nss_type, nss

    def parse_url(self, data: dict, url):
        """Parse one url into identifiers."""
        url_str = get_cdata(url)
        super().parse_url(data, url_str)

    def unparse_identifier(self, data: dict, nid: str, nss: str, primary: bool) -> dict:
        """Unparse one identifier to an xml metron GTIN or ID tag."""
        if gtin_subtag := self.GTIN_SUBTAGS.inverse.get(nid):
            # Unparse GTIN
            if GTIN_TAG not in data:
                data[GTIN_TAG] = {}
            data[GTIN_TAG][gtin_subtag] = nss
        elif nid_value := NID_ORIGIN_MAP.get(nid):
            # Unparse ID
            if IDS_TAG not in data:
                data[IDS_TAG] = {ID_TAG: []}

            id_tag: dict[str, str | bool] = {SOURCE_ATTRIBUTE: nid_value, "#text": nss}
            if primary:
                id_tag[PRIMARY_ATTRIBUTE] = True
            data[IDS_TAG][ID_TAG].append(id_tag)
        return data

    def unparse_urls(
        self, data: dict, nid: str, nss: str, url: str | None, primary: bool
    ) -> dict:
        """Unparse one identifier to an xml metron URL tag."""
        if not url:
            new_identifier = create_identifier(nid, nss)
            url = new_identifier.get(URL_KEY)

        if not url:
            return data

        # Same as parent to here

        if self.URLS_TAG not in data:
            data[self.URLS_TAG] = {self.URLS_SUB_TAG: []}
            primary = True
        else:
            primary = False

        url_tag = {"#text": url}
        if primary:
            url_tag[PRIMARY_ATTRIBUTE] = True

        data[self.URLS_TAG][self.URLS_SUB_TAG].append(url_tag)
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicInfoPagesTransformMixin.parse_pages,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        parse_gtin,
        hoist_metron_resource_lists,
        parse_publisher,
        parse_metron_series,
        hoist_metron_credits,
        map_arcs_to_story_arcs,
        hoist_reprints,
        consolidate_reprints,
        IdentifiersTransformMixin.parse_default_primary_identifier,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicInfoPagesTransformMixin.unparse_pages,
        IdentifiersTransformMixin.unparse_identifiers,
        lower_metron_resource_lists,
        unparse_publisher,
        unparse_metron_series,
        lower_metron_credits,
        map_story_arcs_to_arcs,
        lower_reprints,
    )
