"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from logging import getLogger
from types import MappingProxyType

from bidict import frozenbidict
from comicfn2dict.parse import comicfn2dict

from comicbox.dict_funcs import deep_update
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
    DEFAULT_NID,
    ISBN_NID,
    NID_ORIGIN_MAP,
    UPC_NID,
    create_identifier,
)
from comicbox.schemas.comet import CoMetRoleTagEnum
from comicbox.schemas.comicbookinfo import ComicBookInfoRoleEnum
from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    CHARACTERS_KEY,
    COUNTRY_KEY,
    CREDITS_KEY,
    DATE_KEY,
    DESIGNATION_KEY,
    GENRES_KEY,
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    NAME_KEY,
    NID_KEY,
    NOTES_KEY,
    NUMBER_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PRICE_KEY,
    PRICES_KEY,
    PUBLISHER_KEY,
    REPRINT_ISSUE_KEY,
    REPRINT_SERIES_KEY,
    REPRINTS_KEY,
    ROLES_KEY,
    SERIES_KEY,
    SERIES_SORT_NAME_KEY,
    SERIES_START_YEAR_KEY,
    STORIES_KEY,
    STORY_ARCS_KEY,
    SUMMARY_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
    UPDATED_AT_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.schemas.comicinfo import (
    ComicInfoAgeRatingEnum,
    ComicInfoRoleTagEnum,
)
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.schemas.metroninfo import (
    MetronAgeRatingEnum,
    MetronInfoSchema,
    MetronRoleEnum,
)
from comicbox.transforms.credit_role_tag import create_role_map
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.reprints import reprint_to_filename, sort_reprints
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)

# Move into class.
AGE_RATING_TAG = "AgeRating"
ARCS_TAG = "Arcs"
ARC_NAME_TAG = "Name"
ARC_NUMBER_TAG = "Number"
CHARACTERS_TAG = "Characters"
COUNTRY_ATTRIBUTE = "@country"
CREATOR_TAG = "Creator"
CREDITS_TAG = "Credits"
GTIN_TAG = "GTIN"
IMPRINT_TAG = "Imprint"
IDS_TAG = "IDS"
ID_TAG = "ID"
ID_ATTRIBUTE = "@id"
ISBN_TAG = "ISBN"
UPC_TAG = "UPC"
DESIGNATION_TAG = "Designation"
GENRES_TAG = "Genres"
LOCATIONS_TAG = "Locations"
MANGA_VOLUME_TAG = "MangaVolume"
NAME_TAG = "Name"
PRICES_TAG = "Prices"
PRICE_TAG = "Price"
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
STORY_TAG = "Story"
TEAMS_TAG = "Teams"
TAGS_TAG = "Tags"
UNIVERSES_TAG = "Universes"
UNIVERSE_TAG = "Universe"
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
        # Just hoist
        (IDS_TAG, ID_TAG): IDENTIFIERS_KEY,
        (PRICES_TAG, None): PRICES_KEY,
        (URLS_TAG, None): URL_KEY,
        # Resources
        (CHARACTERS_TAG, None): CHARACTERS_KEY,
        (GENRES_TAG, None): GENRES_KEY,
        (LOCATIONS_TAG, None): LOCATIONS_KEY,
        (TEAMS_TAG, None): TEAMS_KEY,
        (TAGS_TAG, None): TAGS_KEY,
        (STORIES_TAG, STORY_TAG): STORIES_KEY,
        # Add
        (UNIVERSES_TAG, None): UNIVERSES_KEY,
        # Add
        # REPRINTS
        # CREDITS
    }
)
# change to identifier enums
_METRON_RESOURCES = MappingProxyType(
    {
        CHARACTERS_KEY: ("character", CHARACTERS_TAG),
        GENRES_KEY: ("genre", GENRES_TAG),
        LOCATIONS_KEY: ("location", LOCATIONS_TAG),
        STORIES_KEY: ("story", STORIES_TAG),
        TAGS_KEY: ("tag", TAGS_TAG),
        TEAMS_KEY: ("team", TEAMS_TAG),
    }
)


def _copy_assign(key, data, value):
    # used in two locations check on that.
    if value in EMPTY_VALUES:
        return data
    data[key] = value
    return data


class MetronInfoTransform(XmlTransform, IdentifiersTransformMixin):
    """MetronInfo.xml Schema."""

    TRANSFORM_MAP = frozenbidict(
        {
            "CollectionTitle": "collection_title",
            "CoverDate": DATE_KEY,
            "StoreDate": "store_date",
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,
            "Summary": SUMMARY_KEY,
            "LastModified": UPDATED_AT_KEY,
        }
    )
    PRE_ROLE_MAP: MappingProxyType[Enum, Enum | tuple[Enum, ...]] = MappingProxyType(
        {
            **{enum: enum for enum in MetronRoleEnum},
            CoMetRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
            CoMetRoleTagEnum.COVER_DESIGNER: MetronRoleEnum.COVER,
            CoMetRoleTagEnum.CREATOR: MetronRoleEnum.CHIEF_CREATIVE_OFFICER,
            CoMetRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
            CoMetRoleTagEnum.INKER: MetronRoleEnum.INKER,
            CoMetRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
            CoMetRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
            ComicInfoRoleTagEnum.COLORIST: MetronRoleEnum.COLORIST,
            ComicInfoRoleTagEnum.COVER_ARTIST: MetronRoleEnum.COVER,
            ComicInfoRoleTagEnum.EDITOR: MetronRoleEnum.EDITOR,
            ComicInfoRoleTagEnum.INKER: MetronRoleEnum.INKER,
            ComicInfoRoleTagEnum.LETTERER: MetronRoleEnum.LETTERER,
            ComicInfoRoleTagEnum.PENCILLER: MetronRoleEnum.PENCILLER,
            ComicInfoRoleTagEnum.WRITER: MetronRoleEnum.WRITER,
            ComicInfoRoleTagEnum.TRANSLATOR: MetronRoleEnum.TRANSLATOR,
            ComicBookInfoRoleEnum.ARTIST: MetronRoleEnum.ARTIST,
            ComicBookInfoRoleEnum.OTHER: MetronRoleEnum.OTHER,
        }
    )
    ROLE_MAP = create_role_map(PRE_ROLE_MAP)
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
    UNIVERSE_TAG_MAP = frozenbidict({DESIGNATION_TAG: DESIGNATION_KEY})
    GTIN_SUBTAGS = frozenbidict({ISBN_TAG: ISBN_NID, UPC_TAG: UPC_NID})
    SCHEMA_CLASS = MetronInfoSchema
    IDENTIFIERS_TAG = IDS_TAG
    IDENTIFIERS_SUB_TAG = ID_TAG
    URLS_TAG = URLS_TAG
    URLS_SUB_TAG = URL_TAG
    AGE_RATING_TAG = "AgeRating"
    AGE_RATING_MAP = MappingProxyType(
        {
            ComicInfoAgeRatingEnum.EVERYONE: MetronAgeRatingEnum.EVERYONE,
            ComicInfoAgeRatingEnum.EARLY_CHILDHOOD: MetronAgeRatingEnum.EVERYONE,
            ComicInfoAgeRatingEnum.E_10_PLUS: MetronAgeRatingEnum.EVERYONE,
            ComicInfoAgeRatingEnum.G: MetronAgeRatingEnum.EVERYONE,
            ComicInfoAgeRatingEnum.KIDS_TO_ADULTS: MetronAgeRatingEnum.EVERYONE,
            ComicInfoAgeRatingEnum.TEEN: MetronAgeRatingEnum.TEEN,
            ComicInfoAgeRatingEnum.PG: MetronAgeRatingEnum.TEEN,
            ComicInfoAgeRatingEnum.MA_15_PLUS: MetronAgeRatingEnum.TEEN_PLUS,
            ComicInfoAgeRatingEnum.M: MetronAgeRatingEnum.MATURE,
            ComicInfoAgeRatingEnum.MA_17_PLUS: MetronAgeRatingEnum.MATURE,
            ComicInfoAgeRatingEnum.R_18_PLUS: MetronAgeRatingEnum.MATURE,
            ComicInfoAgeRatingEnum.X_18_PLUS: MetronAgeRatingEnum.EXPLICIT,
            ComicInfoAgeRatingEnum.A_18_PLUS: MetronAgeRatingEnum.ADULT,
        }
    )

    def hoist_metron_resource_lists(self, data):
        """Hoist metron resources into comicbox tags."""
        update_dict = {}
        for tags, key in _HOISTABLE_METRON_RESOURCE_TAGS.items():
            # ignores id tag
            tag, single_tag = tags
            if resources := self.hoist_tag(tag, data, single_tag=single_tag):
                update_dict[key] = resources
        if update_dict:
            data.update(update_dict)
        return data

    def lower_metron_resource_lists(self, data):
        """Lower comicbox tags into metron resource tags."""
        update_dict = {}
        for tags, key in _HOISTABLE_METRON_RESOURCE_TAGS.items():
            names = data.pop(key, None)
            if not names:
                continue
            tag, single_tag = tags
            self.lower_tag(tag, tag, update_dict, names, single_tag=single_tag)
        if update_dict:
            data.update(update_dict)
        return data

    def _parse_metron_tag_identifier(
        self, data: dict, nss_type: str, metron_obj: Mapping, comicbox_obj: dict
    ):
        """Parse the metron series identifier."""
        if not (nss := metron_obj.get(ID_ATTRIBUTE)):
            return
        nid = data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY, DEFAULT_NID)
        comicbox_identifier = create_identifier(nid, nss, nss_type=nss_type)
        comicbox_obj[IDENTIFIERS_KEY] = {nid: comicbox_identifier}

    def _parse_imprint(self, data, metron_publisher):
        metron_imprint = metron_publisher.get(IMPRINT_TAG)
        if not metron_imprint:
            return
        imprint_name = get_cdata(metron_imprint)
        if not imprint_name:
            return
        imprint = {NAME_KEY: imprint_name}
        self._parse_metron_tag_identifier(data, "imprint", metron_imprint, imprint)
        if imprint_name:
            data[IMPRINT_KEY] = imprint

    def parse_publisher(self, data):
        """Parse Metron Publisher."""
        metron_publisher = data.pop(PUBLISHER_TAG, None)
        if not metron_publisher:
            return data
        publisher = {NAME_KEY: metron_publisher.get(NAME_TAG)}
        self._parse_metron_tag_identifier(
            data, "publisher", metron_publisher, publisher
        )
        if publisher:
            data[PUBLISHER_KEY] = publisher

        self._parse_imprint(data, metron_publisher)
        return data

    def _parse_identified_name(self, data: dict, nss_type: str, key: str) -> dict:
        """Parse Metron Resource Types into comicbox."""
        if metron_objs := data.get(key):
            comicbox_objs = {}
            for metron_obj in metron_objs:
                name = get_cdata(metron_obj)
                if not name:
                    continue
                comicbox_obj = {}
                if isinstance(metron_obj, Mapping):
                    self._parse_metron_tag_identifier(
                        data, nss_type, metron_obj, comicbox_obj
                    )
                comicbox_objs[name] = comicbox_obj
            if comicbox_objs:
                data[key] = comicbox_objs
        return data

    def parse_metron_resources(self, data: dict) -> dict:
        """Parse Metron Resources."""
        for key, md in _METRON_RESOURCES.items():
            nss_type, _ = md
            data = self._parse_identified_name(data, nss_type, key)
        return data

    def _unparse_identified_name(self, data, name: str, comicbox_obj: dict) -> dict:
        metron_obj = {"#text": name}
        self._unparse_metron_id_attribute(data, metron_obj, comicbox_obj)
        return metron_obj

    def _unparse_identified_names(self, data: dict, tag: str) -> dict:
        """Unparse identifierd names into Metron Resource Types."""
        sub_tag = STORY_TAG if tag == STORIES_TAG else tag[:-1]
        if comicbox_objs := data.get(tag, {}).get(sub_tag):
            metron_objs = []
            for name, comicbox_obj in comicbox_objs.items():
                metron_obj = self._unparse_identified_name(data, name, comicbox_obj)
                metron_objs.append(metron_obj)
            if metron_objs:
                data[tag][sub_tag] = metron_objs
        return data

    def unparse_metron_resources(self, data: dict) -> dict:
        """Unparse comicbox maps into metron Resources."""
        for md in _METRON_RESOURCES.values():
            _, tag = md
            data = self._unparse_identified_names(data, tag)
        return data

    def _unparse_metron_id_attribute(
        self, data: dict, metron_obj: dict, comicbox_obj: dict
    ):
        """Unparse Metron series identifiers from series identifiers."""
        comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
        if not comicbox_identifiers:
            return
        primary_nid = data.get(IDENTIFIER_PRIMARY_SOURCE_KEY, {}).get(NID_KEY)
        for nid, identifier in comicbox_identifiers.items():
            if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
                metron_obj[ID_ATTRIBUTE] = nss
                break

    def unparse_publisher(self, data):
        """Unparse Metron publisher."""
        publisher = data.pop(PUBLISHER_KEY, {})
        publisher_name = publisher.get(NAME_KEY)
        metron_publisher = {}
        if publisher_name:
            metron_publisher[NAME_TAG] = publisher_name
        self._unparse_metron_id_attribute(data, metron_publisher, publisher)
        imprint = data.pop(IMPRINT_KEY, {})
        metron_imprint = {}
        if imprint_name := imprint.get(NAME_KEY):
            metron_imprint["#text"] = imprint_name
        self._unparse_metron_id_attribute(data, metron_imprint, imprint)
        if metron_imprint:
            metron_publisher[IMPRINT_TAG] = metron_imprint
        if metron_publisher:
            data[PUBLISHER_TAG] = metron_publisher
        return data

    def _parse_credit(self, data, metron_credit, comicbox_credits: dict):
        """Copy a single metron style credit entry into comicbox credits."""
        metron_creator = metron_credit.get(CREATOR_TAG, {})
        person_name = get_cdata(metron_creator)
        if not person_name:
            return
        comicbox_credit = {}
        if isinstance(metron_creator, Mapping):
            self._parse_metron_tag_identifier(
                data, "creator", metron_creator, comicbox_credit
            )
        metron_roles = self.hoist_tag(ROLES_TAG, metron_credit)
        if not metron_roles:
            return
        comicbox_roles = {}
        for metron_role in metron_roles:
            metron_role_enum = get_cdata(metron_role)
            if not metron_role_enum:
                continue
            role_name = metron_role_enum.value
            comicbox_role = {}
            if isinstance(metron_role, Mapping):
                self._parse_metron_tag_identifier(
                    data, "role", metron_role, comicbox_role
                )
            comicbox_roles[role_name] = comicbox_role
        if comicbox_roles:
            comicbox_credit[ROLES_KEY] = comicbox_roles
        comicbox_credits[person_name] = comicbox_credit

    def parse_credits(self, data):
        """Copy metron style credits dict into contributors."""
        metron_credits = self.hoist_tag(CREDITS_TAG, data)
        if not metron_credits:
            return data
        comicbox_credits = {}
        for metron_credit in metron_credits:
            try:
                self._parse_credit(data, metron_credit, comicbox_credits)
            except Exception as exc:
                LOG.warning(f"{self._path} Parsing credit {metron_credit}: {exc}")
        return _copy_assign(CREDITS_KEY, data, comicbox_credits)

    def _unparse_credit(self, data, person_name, comicbox_credit, metron_credits):
        """Aggregate comicbox credits into Metron credit dict."""
        if not person_name:
            return
        metron_creator = self._unparse_identified_name(
            data, person_name, comicbox_credit
        )
        metron_credit = {CREATOR_TAG: metron_creator}

        metron_roles = []
        if comicbox_roles := comicbox_credit.get(ROLES_KEY):
            for role_name, comicbox_role in comicbox_roles.items():
                if not role_name:
                    continue
                if metron_role_enum := self.ROLE_MAP.get(role_name.lower()):
                    metron_role = self._unparse_identified_name(
                        data, metron_role_enum, comicbox_role
                    )
                    metron_roles.append(metron_role)
        self.lower_tag(ROLES_TAG, ROLES_TAG, metron_credit, metron_roles)
        metron_credits.append(metron_credit)

    def unparse_credits(self, data):
        """Dump contributors into metron style credits dict."""
        comicbox_credits = data.pop(CREDITS_KEY, None)
        if not comicbox_credits:
            return data
        metron_credits = []
        for person_name, comicbox_credit in comicbox_credits.items():
            try:
                self._unparse_credit(data, person_name, comicbox_credit, metron_credits)
            except Exception as exc:
                LOG.warning(
                    f"{self._path} Parsing credit {person_name}:{comicbox_credit}: {exc}"
                )

        self.lower_tag(CREDITS_TAG, CREDITS_TAG, data, metron_credits)
        return data

    def map_arcs_to_story_arcs(self, data):
        """Convert metron arcs list to story arcs map."""
        if not (metron_arcs := self.hoist_tag(ARCS_TAG, data)):
            return data
        comicbox_story_arcs = {}
        for metron_arc in metron_arcs:
            if not (name := metron_arc.get(ARC_NAME_TAG)):
                continue
            comicbox_story_arc = {}
            number = metron_arc.get(ARC_NUMBER_TAG)
            if number is not None:
                comicbox_story_arc[NUMBER_KEY] = number
            self._parse_metron_tag_identifier(
                data, "story_arc", metron_arc, comicbox_story_arc
            )
            comicbox_story_arcs[name] = comicbox_story_arc
        return _copy_assign(STORY_ARCS_KEY, data, comicbox_story_arcs)

    def map_story_arcs_to_arcs(self, data):
        """Convert story arc dict to metron arcs list."""
        if not (comicbox_story_arcs := data.pop(STORY_ARCS_KEY, None)):
            return data
        metron_arcs = []
        for name, comicbox_story_arc in comicbox_story_arcs.items():
            metron_arc = {ARC_NAME_TAG: name}
            number = comicbox_story_arc.get(NUMBER_KEY)
            if number is not None:
                metron_arc[ARC_NUMBER_TAG] = number
            self._unparse_metron_id_attribute(data, comicbox_story_arc, metron_arc)
            metron_arcs.append(metron_arc)
        self.lower_tag(ARCS_TAG, ARCS_TAG, data, metron_arcs)
        return data

    def parse_gtin(self, data):
        """Parse complex metron gtin structure into identifiers."""
        complex_gtin = data.pop(GTIN_TAG, None)
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
            if isinstance(metron_reprint, Mapping):
                self._parse_metron_tag_identifier(
                    data, "reprint", metron_reprint, new_reprint
                )
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
            if not name:
                continue
            metron_reprint = {"#text": name}
            self._unparse_metron_id_attribute(data, metron_reprint, reprint)
            metron_reprints.append(metron_reprint)
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
        self._parse_metron_tag_identifier(data, "series", metron_series, series)
        if series:
            update_dict[SERIES_KEY] = series

    def _parse_metron_series_volume_key(self, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox volume key."""
        volume = {}

        self._copy_tags(metron_series, volume, self.SERIES_VOLUME_TAG_MAP)

        if number := metron_series.get(SERIES_VOLUME_TAG):
            volume[NUMBER_KEY] = number

        if volume:
            update_dict[VOLUME_KEY] = volume

    def parse_metron_manga_volume(self, data):
        """Parse the metron MangaVolume tag."""
        if volume_name := data.pop(MANGA_VOLUME_TAG, None):
            volume = data.get(VOLUME_KEY, {})
            volume[NAME_KEY] = volume_name
            data[VOLUME_KEY] = volume
        return data

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
            if manga_volume := volume.get(NAME_KEY):
                data[MANGA_VOLUME_TAG] = manga_volume

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

    def parse_prices(self, data: dict) -> dict:
        """Parse prices."""
        if metron_prices := data.pop(PRICES_KEY, None):
            comicbox_prices = []
            for metron_price_obj in metron_prices:
                price = get_cdata(metron_price_obj)
                comicbox_price = {}
                if price is not None:
                    comicbox_price[PRICE_KEY] = price
                if country := metron_price_obj.get(COUNTRY_ATTRIBUTE):
                    comicbox_price[COUNTRY_KEY] = country
                if comicbox_price:
                    comicbox_prices.append(comicbox_price)
            if comicbox_prices:
                data[PRICES_KEY] = comicbox_prices
        return data

    def unparse_prices(self, data: dict) -> dict:
        """Unparse Prices."""
        if comicbox_prices := data.pop(PRICES_TAG, {}).pop(PRICE_TAG, None):
            metron_prices = []
            for comicbox_price in comicbox_prices:
                metron_price = {}
                price = comicbox_price.get(PRICE_KEY)
                if price is not None:
                    metron_price["#text"] = str(
                        Decimal(price).quantize(Decimal("0.01"))
                    )
                    if country := comicbox_price.get(
                        COUNTRY_KEY, data.get(COUNTRY_KEY)
                    ):
                        metron_price[COUNTRY_ATTRIBUTE] = country
                if metron_price:
                    metron_prices.append(metron_price)
            if metron_prices:
                prices = {PRICE_TAG: metron_prices}
                data[PRICES_TAG] = prices
        return data

    def parse_universes(self, data: dict) -> dict:
        """Parse Universes."""
        if metron_universes := data.pop(UNIVERSES_KEY, None):
            comicbox_universes = {}
            for metron_universe in metron_universes:
                name = metron_universe.get(NAME_TAG)
                if not name:
                    continue
                comicbox_universe = {}
                for tag, key in self.UNIVERSE_TAG_MAP.items():
                    if value := metron_universe.get(tag):
                        comicbox_universe[key] = value
                self._parse_metron_tag_identifier(
                    data, "universe", metron_universe, comicbox_universe
                )
                if comicbox_universe:
                    comicbox_universes[name] = comicbox_universe
            if comicbox_universes:
                data[UNIVERSES_KEY] = comicbox_universes
        return data

    def unparse_universes(self, data: dict) -> dict:
        """Unparse Universes."""
        if comicbox_universes := data.pop(UNIVERSES_KEY, {}):
            metron_universes = []
            for name, comicbox_universe in comicbox_universes.items():
                if not name:
                    continue
                metron_universe = {NAME_TAG: name}
                for tag, key in self.UNIVERSE_TAG_MAP.items():
                    if value := comicbox_universe.get(key):
                        metron_universe[tag] = value
                self._unparse_metron_id_attribute(
                    data, metron_universe, comicbox_universe
                )
                if metron_universe:
                    metron_universes.append(metron_universe)
            if metron_universes:
                data[UNIVERSES_KEY] = metron_universes
        return data

    def parse_age_rating(self, data: dict) -> dict:
        """Parse Age Rating."""
        if age_rating_enum := data.pop(AGE_RATING_TAG, None):
            data[AGE_RATING_KEY] = age_rating_enum.value
        return data

    def unparse_age_rating(self, data: dict) -> dict:
        """Unparse Age Rating."""
        if age_rating := data.pop(AGE_RATING_KEY, None):
            metron_enum = None
            try:
                metron_enum = MetronAgeRatingEnum(age_rating)
            except ValueError:
                try:
                    cix_enum = ComicInfoAgeRatingEnum(age_rating)
                    metron_enum = self.AGE_RATING_MAP.get(cix_enum)
                except ValueError:
                    pass
            if metron_enum:
                data[AGE_RATING_TAG] = metron_enum
        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        IdentifiersTransformMixin.parse_identifiers,
        IdentifiersTransformMixin.parse_urls,
        parse_gtin,
        hoist_metron_resource_lists,
        parse_publisher,
        parse_metron_series,
        parse_metron_manga_volume,
        parse_credits,
        map_arcs_to_story_arcs,
        hoist_reprints,
        consolidate_reprints,
        IdentifiersTransformMixin.parse_default_primary_identifier,
        parse_metron_resources,
        parse_prices,
        parse_universes,
        parse_age_rating,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        IdentifiersTransformMixin.unparse_identifiers,
        unparse_universes,
        lower_metron_resource_lists,
        unparse_publisher,
        unparse_metron_series,
        unparse_credits,
        map_story_arcs_to_arcs,
        lower_reprints,
        unparse_metron_resources,
        unparse_prices,
        unparse_age_rating,
    )
