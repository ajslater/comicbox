"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Sequence
from logging import getLogger
from types import MappingProxyType

from bidict import bidict
from comicfn2dict.parse import comicfn2dict

from comicbox.dict_funcs import sort_dict
from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    COMICVINE_NID,
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
    IDENTIFIERS_KEY,
    INKER_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LETTERER_KEY,
    LOCATIONS_KEY,
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
    SERIES_NAME_KEY,
    STORIES_KEY,
    STORY_ARCS_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
    WRITER_KEY,
)
from comicbox.schemas.identifier import NSS_KEY
from comicbox.schemas.metroninfo import MetronInfoSchema
from comicbox.transforms.comicinfo_pages import ComicInfoPagesTransformMixin
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.reprints import reprint_to_filename, sort_reprints
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)

ARCS_TAG = "Arcs"
ARC_NAME_TAG = "Name"
ARC_NUMBER_TAG = "Number"
ARC_ID_TAG = "@id"
CHARACTERS_TAG = "Characters"
CREATOR_TAG = "Creator"
GTIN_TAG = "GTIN"
ISBN_TAG = "ISBN"
UPC_TAG = "UPC"
ROLES_TAG = "Roles"
CREDITS_TAG = "Credits"
GENRES_TAG = "Genres"
LOCATIONS_TAG = "Locations"
PRICES_TAG = "Prices"
PUBLISHER_TAG = "Publisher"
REPRINTS_TAG = "Reprints"
SERIES_TAG = "Series"
SERIES_NAME_TAG = "Name"
SERIES_VOLUME_TAG = "Volume"
SERIES_FORMAT_TAG = "Format"
SERIES_LANG_TAG = "@lang"
SERIES_ID_TAG = "@id"
ID_TAG = "ID"
STORIES_TAG = "Stories"
TEAMS_TAG = "Teams"
TAGS_TAG = "Tags"

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
        (LOCATIONS_TAG, None): LOCATIONS_KEY,
        (PRICES_TAG, None): PRICE_KEY,
        (STORIES_TAG, "Story"): STORIES_KEY,
        (TEAMS_TAG, None): TEAMS_KEY,
        (TAGS_TAG, None): TAGS_KEY,
    }
)
_PARSABLE_METRON_RESOURCE_TAGS = MappingProxyType({PUBLISHER_TAG: PUBLISHER_KEY})


def _copy_assign(key, data, value):
    if not value:
        return data
    data[key] = value
    return data


class MetronInfoTransform(ComicInfoPagesTransformMixin, IdentifiersTransformMixin):
    """MetronInfo.xml Schema."""

    TRANSFORM_MAP = bidict(
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
    SCHEMA_CLASS = MetronInfoSchema
    URL_TAG = "URL"

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

    def parse_metron_single_resources(self, data):
        """Parse Metron resource tags."""
        update_dict = {}
        for tag, key in _PARSABLE_METRON_RESOURCE_TAGS.items():
            name = get_cdata(data.pop(tag, {}))
            if name:
                update_dict[key] = name
        if update_dict:
            data.update(update_dict)
        return data

    def unparse_metron_single_resources(self, data):
        """Unparse Metron resource tags."""
        update_dict = {}
        for tag, key in _PARSABLE_METRON_RESOURCE_TAGS.items():
            name = data.pop(key, None)
            if name:
                update_dict[tag] = {"#text": name}
        if update_dict:
            data.update(update_dict)
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
        identifiers = {}
        isbn = complex_gtin.get(ISBN_TAG)
        upc = complex_gtin.get(UPC_TAG)
        if isbn:
            identifiers[ISBN_NID] = {NSS_KEY: isbn}
        if upc:
            identifiers[UPC_NID] = {NSS_KEY: upc}
        return _copy_assign(IDENTIFIERS_KEY, data, identifiers)

    def unparse_gtin(self, data):
        """Unparse identifiers into metron complex gtin structure."""
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return data
        complex_gtin = {}
        if isbn := identifiers.get(ISBN_NID, {}).get(NSS_KEY):
            complex_gtin[ISBN_TAG] = isbn
        if upc := identifiers.get(UPC_NID, {}).get(NSS_KEY):
            complex_gtin[UPC_TAG] = upc
        return _copy_assign(GTIN_TAG, data, complex_gtin)

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
                new_reprint[REPRINT_SERIES_KEY] = {SERIES_NAME_KEY: series}
            issue = fn_dict.get(ISSUE_KEY)
            if issue is not None:
                new_reprint[REPRINT_ISSUE_KEY] = issue
            if new_reprint:
                comicbox_reprints.append(new_reprint)
        comicbox_reprints = sort_reprints(comicbox_reprints)
        return _copy_assign(REPRINTS_KEY, data, comicbox_reprints)

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

    @staticmethod
    def _parse_metron_series_identifier(series_nss, data):
        nid = data.pop(ID_TAG, COMICVINE_NID)
        if not series_nss:
            return

        if not data.get(SERIES_KEY):
            data[SERIES_KEY] = {}
        if not data[SERIES_KEY][IDENTIFIERS_KEY]:
            data[SERIES_KEY][IDENTIFIERS_KEY] = {}

        old_identifiers = data[SERIES_KEY][IDENTIFIERS_KEY]

        old_identifier = old_identifiers.get(nid)
        if not old_identifier:
            identifier = create_identifier(nid, series_nss)
            old_identifiers[nid] = identifier

    def parse_metron_series(self, data):
        """Parse complex metron series into comicbox data."""
        metron_series = data.pop(SERIES_TAG, None)
        if not metron_series:
            return data
        update_dict = {}
        if series := metron_series.get(SERIES_NAME_TAG):
            if SERIES_KEY not in update_dict:
                update_dict[SERIES_KEY] = {}
            update_dict[SERIES_KEY][SERIES_NAME_KEY] = series
        if volume := metron_series.get(SERIES_VOLUME_TAG):
            if VOLUME_KEY not in update_dict:
                update_dict[VOLUME_KEY] = {}
            update_dict[VOLUME_KEY][VOLUME_NUMBER_KEY] = volume
        if original_format := metron_series.get(SERIES_FORMAT_TAG):
            update_dict[ORIGINAL_FORMAT_KEY] = original_format
        if language := metron_series.get(SERIES_LANG_TAG):
            update_dict[LANGUAGE_KEY] = language

        series_nss = metron_series.get(SERIES_ID_TAG)

        if update_dict:
            data.update(update_dict)

        self._parse_metron_series_identifier(series_nss, data)

        return data

    def unparse_metron_series(self, data):
        """Unparse the data into the complex metron series tag."""
        metron_series = {}
        if series := data.get(SERIES_KEY):
            metron_series[SERIES_NAME_TAG] = series.get(SERIES_NAME_KEY)
            identifiers = series.get(IDENTIFIERS_KEY, {})
            for nid, identifier in identifiers.items():
                if nss := identifier.get(NSS_KEY):
                    metron_series[SERIES_ID_TAG] = nss
                    metron_id_origin = NID_ORIGIN_MAP.get(nid)
                    data = _copy_assign(ID_TAG, data, {"@source": metron_id_origin})
                    break

        if volume := data.get(VOLUME_KEY, {}).get(VOLUME_NUMBER_KEY):
            metron_series[SERIES_VOLUME_TAG] = volume
        if original_format := data.get(ORIGINAL_FORMAT_KEY):
            metron_series[SERIES_FORMAT_TAG] = original_format
        if language := data.get(LANGUAGE_KEY):
            metron_series[SERIES_LANG_TAG] = language

        return _copy_assign(SERIES_TAG, data, metron_series)

    def unparse_metron_id_source(self, data):
        """Get the metron ID source from the identifiers."""
        if data.get(ID_TAG, {}).get("@source"):
            return data
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return data
        for nid in identifiers:
            metron_id_origin = NID_ORIGIN_MAP.get(nid)
            if metron_id_origin:
                return _copy_assign(ID_TAG, data, {"@source": metron_id_origin})
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        ComicInfoPagesTransformMixin.parse_pages,
        hoist_metron_resource_lists,
        parse_metron_single_resources,
        parse_metron_series,
        hoist_metron_credits,
        map_arcs_to_story_arcs,
        parse_gtin,
        hoist_reprints,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        ComicInfoPagesTransformMixin.unparse_pages,
        lower_metron_resource_lists,
        unparse_metron_single_resources,
        unparse_metron_series,
        lower_metron_credits,
        map_story_arcs_to_arcs,
        unparse_gtin,
        lower_reprints,
        unparse_metron_id_source,
        IdentifiersTransformMixin.unparse_url_tag,
    )
