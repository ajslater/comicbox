"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Callable, Mapping
from decimal import Decimal
from enum import Enum
from logging import getLogger
from types import MappingProxyType
from typing import Any

from bidict import frozenbidict
from comicfn2dict.parse import comicfn2dict

from comicbox.dict_funcs import deep_update
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import (
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
    CREDITS_KEY,
    DATE_KEY,
    DESIGNATION_KEY,
    GENRES_KEY,
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    ISSUE_KEY,
    LANGUAGE_KEY,
    LOCATIONS_KEY,
    NAME_KEY,
    NOTES_KEY,
    NUMBER_KEY,
    NUMBER_TO_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
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
SERIES_REPRINTS_KEY = "series_reprints"


_NESTED_METRON_RESOURCE_TAGS = frozenbidict(
    {
        STORY_ARCS_KEY: ARCS_TAG,
        CHARACTERS_KEY: CHARACTERS_TAG,
        CREDITS_KEY: CREDITS_TAG,
        GENRES_KEY: GENRES_TAG,
        IDENTIFIERS_KEY: IDS_TAG,
        LOCATIONS_KEY: LOCATIONS_TAG,
        PRICES_KEY: PRICES_TAG,
        REPRINTS_KEY: REPRINTS_TAG,
        ROLES_KEY: ROLES_TAG,
        STORIES_KEY: STORIES_TAG,
        TAGS_KEY: TAGS_TAG,
        TEAMS_KEY: TEAMS_TAG,
        UNIVERSES_KEY: UNIVERSES_TAG,
        URL_KEY: URLS_TAG,
    }
)
_IRREGULAR_SINGLE_TAGS = MappingProxyType({IDS_TAG: ID_TAG, STORIES_TAG: STORY_TAG})
_METRON_RESOURCES = MappingProxyType(
    {
        CHARACTERS_KEY: "character",
        GENRES_KEY: "genre",
        LOCATIONS_KEY: "location",
        STORIES_KEY: "story",
        TAGS_KEY: "tag",
        TEAMS_KEY: "team",
    }
)


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
    URLS_TAG = URLS_TAG
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

    # UTILITY
    ###########################################################################
    @staticmethod
    def _copy_tags(from_dict, to_dict, tag_dict):
        for from_key, to_key in tag_dict.items():
            if value := from_dict.get(from_key):
                to_dict[to_key] = value

    # ID ATTRIBUTE
    ###########################################################################
    @classmethod
    def _parse_metron_id_attribute(
        cls, data: dict, nss_type: str, metron_obj: Mapping | str, comicbox_obj: dict
    ):
        """Parse the metron series identifier."""
        try:
            if not (
                isinstance(metron_obj, Mapping)
                and (nss := metron_obj.get(ID_ATTRIBUTE))
            ):
                return
            primary_nid = cls.get_primary_source_nid(data)
            comicbox_identifier = create_identifier(primary_nid, nss, nss_type=nss_type)
            comicbox_obj[IDENTIFIERS_KEY] = {primary_nid: comicbox_identifier}
        except Exception as exc:
            LOG.warning(
                f"Parsing metron tag identifier {nss_type}:{metron_obj} - {exc}"
            )

    @classmethod
    def _unparse_metron_id_attribute(
        cls, data: dict, metron_obj: dict, comicbox_obj: dict
    ):
        """Unparse Metron series identifiers from series identifiers."""
        comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
        if not comicbox_identifiers:
            return
        primary_nid = cls.get_primary_source_nid(data)
        for nid, identifier in comicbox_identifiers.items():
            if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
                metron_obj[ID_ATTRIBUTE] = nss
                break

    # NESTED TAGS
    ###########################################################################
    @staticmethod
    def _hoist_metron_tag(base_obj: dict, tag: str):
        metron_objs = base_obj.pop(tag, None)
        if not metron_objs:
            return None
        single_tag = _IRREGULAR_SINGLE_TAGS.get(tag, tag[:-1])
        return metron_objs.get(single_tag)

    @classmethod
    def _parse_metron_tag(
        cls,
        base_obj: dict,
        tag: str,
        parse_method: Callable[[dict, dict | str], tuple[str, dict]],
        *args,
        list_type: bool = False,
        data: dict | None = None,
        **kwargs,
    ) -> dict:
        """Parse a single metron tag with a submitted parser method."""
        metron_objs = cls._hoist_metron_tag(base_obj, tag)
        if not metron_objs:
            return base_obj
        comicbox_objs = [] if list_type else {}
        if data is None:
            data = base_obj
        for metron_obj in metron_objs:
            sub_key, comicbox_obj = parse_method(data, metron_obj, *args, **kwargs)
            if sub_key:
                if isinstance(comicbox_objs, list):
                    comicbox_objs.append(comicbox_obj)
                else:
                    comicbox_objs[sub_key] = comicbox_obj
        if comicbox_objs not in EMPTY_VALUES:
            key = _NESTED_METRON_RESOURCE_TAGS.inverse[tag]
            base_obj[key] = comicbox_objs
        return base_obj

    @staticmethod
    def _lower_metron_tag(base_obj: dict, key: str, value) -> dict:
        if value in EMPTY_VALUES:
            return base_obj
        tag = _NESTED_METRON_RESOURCE_TAGS[key]
        single_tag = _IRREGULAR_SINGLE_TAGS.get(tag, tag[:-1])
        base_obj[tag] = {single_tag: value}
        return base_obj

    @classmethod
    def _unparse_metron_tag(
        cls,
        base_obj: dict,
        key: str,
        unparse_method: Callable[[dict, str, Any], dict],
        *args,
        list_type: bool = False,
        data: dict | None = None,
        **kwargs,
    ) -> dict:
        """Unparse a single metron tag with a submitted unparse method."""
        comicbox_objs = base_obj.pop(key, None)
        if not comicbox_objs:
            return base_obj
        metron_objs = []
        if data is None:
            data = base_obj
        for sub_key in comicbox_objs:
            sub_value = sub_key if list_type else comicbox_objs[sub_key]
            metron_obj = unparse_method(data, sub_key, sub_value, *args, **kwargs)
            if metron_obj:
                metron_objs.append(metron_obj)
        return cls._lower_metron_tag(base_obj, key, metron_objs)

    # IDENTIFIED NAME TAG
    ###########################################################################
    @classmethod
    def _parse_identified_name(
        cls, data: dict, metron_obj: dict | str, nss_type: str
    ) -> tuple[str, dict]:
        comicbox_obj = {}
        if not (name := get_cdata(metron_obj)):
            return ("", comicbox_obj)
        if isinstance(name, Enum):
            name = name.value
        cls._parse_metron_id_attribute(data, nss_type, metron_obj, comicbox_obj)
        return name, comicbox_obj

    @classmethod
    def _unparse_identified_name(
        cls, data: dict, name: str, comicbox_obj: dict
    ) -> dict:
        metron_obj = {"#text": name}
        cls._unparse_metron_id_attribute(data, metron_obj, comicbox_obj)
        return metron_obj

    # AGE RATING
    ###########################################################################
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

    # RESOURCES
    ###########################################################################
    def parse_resources(self, data: dict) -> dict:
        """Parse Metron Resources."""
        for key, nss_type in _METRON_RESOURCES.items():
            tag = _NESTED_METRON_RESOURCE_TAGS[key]
            data = self._parse_metron_tag(
                data,
                tag,
                # TODO Don't know how to specify optional args to the Callable type
                self._parse_identified_name,  # type: ignore[reportInvalidTypeForm]
                nss_type,
            )
        return data

    def unparse_resources(self, data: dict) -> dict:
        """Unparse comicbox maps into metron Resources."""
        for key in _METRON_RESOURCES:
            data = self._unparse_metron_tag(data, key, self._unparse_identified_name)
        return data

    # ARCS
    ###########################################################################
    @classmethod
    def _parse_arc(cls, data, metron_arc) -> tuple[str, dict]:
        """Parse one metron Arc."""
        comicbox_story_arc = {}
        if not (name := metron_arc.get(ARC_NAME_TAG, "")):
            return (name, comicbox_story_arc)
        number = metron_arc.get(ARC_NUMBER_TAG)
        if number is not None:
            comicbox_story_arc[NUMBER_KEY] = number
        cls._parse_metron_id_attribute(
            data, "story_arc", metron_arc, comicbox_story_arc
        )
        return name, comicbox_story_arc

    def parse_arcs(self, data):
        """Convert metron arcs list to story arcs map."""
        return self._parse_metron_tag(data, ARCS_TAG, self._parse_arc)

    @classmethod
    def _unparse_arc(cls, data, name, comicbox_story_arc: dict) -> dict:
        """Unparse one metron Arc."""
        metron_arc = {ARC_NAME_TAG: name}
        number = comicbox_story_arc.get(NUMBER_KEY)
        if number is not None:
            metron_arc[ARC_NUMBER_TAG] = number
        cls._unparse_metron_id_attribute(data, comicbox_story_arc, metron_arc)
        return metron_arc

    def unparse_arcs(self, data):
        """Convert story arc dict to metron arcs list."""
        return self._unparse_metron_tag(data, STORY_ARCS_KEY, self._unparse_arc)

    # PRICES
    ###########################################################################
    @staticmethod
    def _parse_price(_data, metron_price) -> tuple[str, dict]:
        """Parse a metron Price."""
        price = get_cdata(metron_price)
        if price is None:
            return "", {}
        country = metron_price.get(COUNTRY_ATTRIBUTE, "")
        # TODO allow empty countries later
        return country, price

    def parse_prices(self, data: dict) -> dict:
        """Parse prices."""
        return self._parse_metron_tag(data, PRICES_TAG, self._parse_price)

    @staticmethod
    def _unparse_price(_data, country, price) -> dict:
        """Unparse a metron Price."""
        if price is None:
            return {}
        metron_price = {
            "#text": str(Decimal(price).quantize(Decimal("0.01"))),
        }
        if country:
            metron_price[COUNTRY_ATTRIBUTE] = country
        return metron_price

    def unparse_prices(self, data: dict) -> dict:
        """Unparse Prices."""
        return self._unparse_metron_tag(data, PRICES_KEY, self._unparse_price)

    # UNIVERSES
    ###########################################################################
    @classmethod
    def _parse_universe(cls, data: dict, metron_universe) -> tuple[str, dict]:
        """Parse metron Universe."""
        name = metron_universe.get(NAME_TAG, "")
        comicbox_universe = {}
        if not name:
            return name, comicbox_universe
        for tag, key in cls.UNIVERSE_TAG_MAP.items():
            if value := metron_universe.get(tag):
                comicbox_universe[key] = value
        cls._parse_metron_id_attribute(
            data, "universe", metron_universe, comicbox_universe
        )
        return name, comicbox_universe

    def parse_universes(self, data: dict) -> dict:
        """Parse Universes."""
        return self._parse_metron_tag(data, UNIVERSES_TAG, self._parse_universe)

    @classmethod
    def _unparse_universe(cls, data: dict, name: str, comicbox_universe) -> dict:
        """Unparse metron Universe."""
        if not name:
            return {}
        metron_universe = {NAME_TAG: name}
        for tag, key in cls.UNIVERSE_TAG_MAP.items():
            if value := comicbox_universe.get(key):
                metron_universe[tag] = value
        cls._unparse_metron_id_attribute(data, metron_universe, comicbox_universe)
        return metron_universe

    def unparse_universes(self, data: dict) -> dict:
        """Unparse Universes."""
        return self._unparse_metron_tag(data, UNIVERSES_KEY, self._unparse_universe)

    # IDENTIFIERS & URLS
    ###########################################################################
    @staticmethod
    def parse_item_primary(native_identifier) -> bool:
        """Parse primary attribute."""
        return (
            bool(native_identifier.get(PRIMARY_ATTRIBUTE))
            if isinstance(native_identifier, Mapping)
            else False
        )

    @classmethod
    def parse_identifier_native(cls, native_identifier) -> tuple[str, str, str]:
        """Parse metron identifier type into components."""
        source = native_identifier.get(SOURCE_ATTRIBUTE, "")  # type: ignore[reportAttributeAccessIssue]
        if isinstance(source, Enum):
            source = source.value
        nid = NID_ORIGIN_MAP.inverse.get(source, "")
        nss_type = "issue"
        nss = get_cdata(native_identifier) or "" if nid else ""
        return nid, nss_type, nss

    def parse_identifiers(self, data: dict) -> dict:
        """Hoist Identifiers before parsing."""
        return self._parse_metron_tag(data, self.IDENTIFIERS_TAG, self.parse_identifier)

    def parse_urls(self, data: dict) -> dict:
        """Parse URLs."""
        return self._parse_metron_tag(data, self.URLS_TAG, self.parse_url)

    def parse_gtin(self, data):
        """Parse complex metron gtin structure into identifiers."""
        complex_gtin = data.pop(GTIN_TAG, None)
        if not complex_gtin:
            return data
        comicbox_identifiers = {}
        for tag, nid in self.GTIN_SUBTAGS.items():
            if nss := complex_gtin.get(tag):
                identifier = create_identifier(nid, nss)
                comicbox_identifiers[nid] = identifier
        self.merge_identifiers(data, comicbox_identifiers)
        return data

    @classmethod
    def _unparse_gtin_from_identifier(cls, data, nid: str, nss: str):
        """Unparse GTIN from identifier."""
        gtin_subtag = cls.GTIN_SUBTAGS.inverse.get(nid)
        if not gtin_subtag:
            return False
        if GTIN_TAG not in data:
            data[GTIN_TAG] = {}
        data[GTIN_TAG][gtin_subtag] = nss
        return True

    @classmethod
    def unparse_url(cls, data: dict, nid: str, comicbox_identifier: dict) -> dict:
        """Unparse one identifier to an xml metron URL tag."""
        metron_url = super().unparse_url(data, nid, comicbox_identifier)

        primary_nid = cls.get_primary_source_nid(data)
        if nid == primary_nid:
            # This works here because these are added one at a time with the side effect
            metron_url[PRIMARY_ATTRIBUTE] = True

        return metron_url

    @classmethod
    def unparse_identifier(
        cls, data: dict, nid: str, comicbox_identifier: dict
    ) -> dict:
        """Unparse one identifier to an xml metron GTIN or ID tag."""
        metron_identifier = {}
        nss = comicbox_identifier.get(NSS_KEY, "")
        if (
            nss
            and (not cls._unparse_gtin_from_identifier(data, nid, nss))
            and (nid_value := NID_ORIGIN_MAP.get(nid))
        ):
            metron_identifier = {SOURCE_ATTRIBUTE: nid_value, "#text": nss}
            primary_nid = cls.get_primary_source_nid(data)
            if nid == primary_nid:
                metron_identifier[PRIMARY_ATTRIBUTE] = True

        # Side effect
        if metron_url := cls.unparse_url(data, nid, comicbox_identifier):
            if URLS_TAG not in data:
                data[URLS_TAG] = []
            data[URLS_TAG].append(metron_url)

        return metron_identifier

    def unparse_identifiers(self, data: dict) -> dict:
        """Lower Identifiers after unparsing."""
        data = self._unparse_metron_tag(data, IDENTIFIERS_KEY, self.unparse_identifier)
        if urls := data.pop(URLS_TAG, None):
            data = self._lower_metron_tag(data, URL_KEY, urls)
        return data

    # CREDITS
    ###########################################################################
    def _parse_credit(self, data: dict, metron_credit) -> tuple[str, dict]:
        """Copy a single metron style credit entry into comicbox credits."""
        metron_creator = metron_credit.pop(CREATOR_TAG, {})
        person_name, comicbox_credit = self._parse_identified_name(
            data, metron_creator, "creator"
        )
        comicbox_credit = self._parse_metron_tag(
            metron_credit,
            ROLES_TAG,
            # TODO Don't know how to specify optional args to the Callable type
            self._parse_identified_name,  # type: ignore[reportInvalidTypeForm]
            "role",
            data=data,
        )
        return person_name, comicbox_credit

    def parse_credits(self, data: dict):
        """Copy metron style credits dict into contributors."""
        return self._parse_metron_tag(data, CREDITS_TAG, self._parse_credit)

    @classmethod
    def _unparse_role(cls, data, role_name, comicbox_role):
        """Unparse a metron role to an enum only value."""
        if role_name and (metron_role_enum := cls.ROLE_MAP.get(role_name.lower())):
            return cls._unparse_identified_name(data, metron_role_enum, comicbox_role)
        return {}

    @classmethod
    def _unparse_credit(
        cls, data: dict, person_name: str, comicbox_credit: dict
    ) -> dict:
        """Aggregate comicbox credits into Metron credit dict."""
        if not person_name:
            return {}
        metron_creator = cls._unparse_identified_name(
            data, person_name, comicbox_credit
        )
        metron_credit = {CREATOR_TAG: metron_creator}
        metron_roles = cls._unparse_metron_tag(
            comicbox_credit, ROLES_KEY, cls._unparse_role, data=data
        )
        metron_credit.update(metron_roles)
        return metron_credit

    def unparse_credits(self, data):
        """Dump contributors into metron style credits dict."""
        return self._unparse_metron_tag(data, CREDITS_KEY, self._unparse_credit)

    # REPRINTS
    ###########################################################################
    @classmethod
    def _parse_reprint(cls, data, metron_reprint) -> tuple[str, dict]:
        """Parse a metron Reprint."""
        comicbox_reprint = {}
        name = get_cdata(metron_reprint)
        if not name:
            return "", comicbox_reprint
        fn_dict = comicfn2dict(name)
        series = fn_dict.get(SERIES_KEY)
        if series:
            comicbox_reprint[REPRINT_SERIES_KEY] = {NAME_KEY: series}
        issue = fn_dict.get(ISSUE_KEY)
        if issue is not None:
            comicbox_reprint[REPRINT_ISSUE_KEY] = issue
        cls._parse_metron_id_attribute(
            data, "reprint", metron_reprint, comicbox_reprint
        )
        return name, comicbox_reprint

    def parse_reprints(self, data):
        """Parse a metron Reprint."""
        return self._parse_metron_tag(
            data, REPRINTS_TAG, self._parse_reprint, list_type=True
        )

    @staticmethod
    def _aggregate_reprints(reprints, new_reprint):
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
        """Consolidate reprints after parsing from both series & reprints."""
        old_reprints = data.pop(REPRINTS_KEY, [])
        series_reprints = data.pop(SERIES_REPRINTS_KEY, [])
        consolidated_reprints = []
        for reprint in old_reprints + series_reprints:
            self._aggregate_reprints(consolidated_reprints, reprint)
        if consolidated_reprints:
            data[REPRINTS_KEY] = sort_reprints(consolidated_reprints)
        return data

    @classmethod
    def _unparse_reprint(cls, data, _, comicbox_reprint) -> dict:
        """Unparse a structured comicbox reprints into metron reprint."""
        name = reprint_to_filename(comicbox_reprint)
        if not name:
            return {}
        metron_reprint = {"#text": name}
        cls._unparse_metron_id_attribute(data, metron_reprint, comicbox_reprint)
        return metron_reprint

    def unparse_reprints(self, data):
        """Unparse reprint structures into metron reprint names."""
        return self._unparse_metron_tag(
            data, REPRINTS_KEY, self._unparse_reprint, list_type=True
        )

    # PUBLISHER
    ###########################################################################
    @classmethod
    def _parse_imprint(cls, data, metron_publisher):
        metron_imprint = metron_publisher.get(IMPRINT_TAG)
        if not metron_imprint:
            return
        imprint_name = get_cdata(metron_imprint)
        if not imprint_name:
            return
        imprint = {NAME_KEY: imprint_name}
        cls._parse_metron_id_attribute(data, "imprint", metron_imprint, imprint)
        if imprint_name:
            data[IMPRINT_KEY] = imprint

    def parse_publisher(self, data):
        """Parse Metron Publisher."""
        metron_publisher = data.pop(PUBLISHER_TAG, None)
        if not metron_publisher:
            return data
        publisher = {NAME_KEY: metron_publisher.get(NAME_TAG)}
        self._parse_metron_id_attribute(data, "publisher", metron_publisher, publisher)
        if publisher:
            data[PUBLISHER_KEY] = publisher

        self._parse_imprint(data, metron_publisher)
        return data

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

    # SERIES
    ###########################################################################
    @classmethod
    def _parse_series_series_key(cls, data, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox series key."""
        series = {}

        cls._copy_tags(metron_series, series, cls.SERIES_TAG_MAP)
        cls._parse_metron_id_attribute(data, "series", metron_series, series)
        if series:
            update_dict[SERIES_KEY] = series

    @classmethod
    def _parse_series_volume_key(cls, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox volume key."""
        volume = {}

        cls._copy_tags(metron_series, volume, cls.SERIES_VOLUME_TAG_MAP)

        if number := metron_series.get(SERIES_VOLUME_TAG):
            volume[NUMBER_KEY] = number

        if volume:
            update_dict[VOLUME_KEY] = volume

    @staticmethod
    def _parse_series_alternative_names(data, metron_series) -> dict:
        """Parse metron series alternative name tags into reprints."""
        alternative_names = metron_series.get(SERIES_ALTERNATIVE_NAMES_TAG)
        if not alternative_names:
            return data
        alternative_names = alternative_names.get(SERIES_ALTERNATIVE_NAME_TAG)
        if not alternative_names:
            return data
        reprints = []
        aliases = set()

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

        if reprints:
            data[SERIES_REPRINTS_KEY] = reprints
        return data

    def parse_series(self, data):
        """Parse complex metron series into comicbox data."""
        metron_series = data.pop(SERIES_TAG, None)
        if not metron_series:
            return data
        update_dict = {}

        if language := metron_series.get(SERIES_LANG_ATTRIBUTE):
            update_dict[LANGUAGE_KEY] = language
        self._parse_series_series_key(data, metron_series, update_dict)
        self._parse_series_volume_key(metron_series, update_dict)
        if original_format := metron_series.get(SERIES_FORMAT_TAG):
            update_dict[ORIGINAL_FORMAT_KEY] = original_format.value
        data = self._parse_series_alternative_names(data, metron_series)

        if update_dict:
            deep_update(data, update_dict)

        return data

    def parse_manga_volume(self, data):
        """Parse the metron MangaVolume tag."""
        if manga_volume_name := data.pop(MANGA_VOLUME_TAG, None):
            volume = data.get(VOLUME_KEY, {})
            parts = manga_volume_name.split("-")
            if NUMBER_KEY not in volume:
                volume[NUMBER_KEY] = parts[0]
            if len(parts) > 1:
                volume[NUMBER_TO_KEY] = parts[1]
            data[VOLUME_KEY] = volume
        return data

    @staticmethod
    def _unparse_series_alternative_names(data, metron_series):
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

    def unparse_series(self, data):
        """Unparse the data into the complex metron series tag."""
        metron_series = {}
        if language := data.get(LANGUAGE_KEY):
            metron_series[SERIES_LANG_ATTRIBUTE] = language

        if series := data.get(SERIES_KEY):
            self._copy_tags(series, metron_series, self.SERIES_TAG_MAP.inverse)
            self._unparse_metron_id_attribute(data, metron_series, series)

        if volume := data.get(VOLUME_KEY):
            self._copy_tags(volume, metron_series, self.SERIES_VOLUME_TAG_MAP.inverse)
            number = volume.get(NUMBER_KEY)
            number_to = volume.get(NUMBER_TO_KEY)
            if number is not None and number_to is not None:
                data[MANGA_VOLUME_TAG] = f"{number}-{number_to}"

        if original_format := data.get(ORIGINAL_FORMAT_KEY):
            metron_series[SERIES_FORMAT_TAG] = original_format

        # Add series id
        self._unparse_series_alternative_names(data, metron_series)

        if metron_series:
            if SERIES_TAG not in data:
                data[SERIES_TAG] = {}
            deep_update(data[SERIES_TAG], metron_series)

        return data

    TO_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.TO_COMICBOX_PRE_TRANSFORM,
        parse_identifiers,
        parse_urls,
        parse_gtin,
        IdentifiersTransformMixin.parse_default_primary_identifier,
        parse_age_rating,
        parse_arcs,
        parse_credits,
        parse_manga_volume,
        parse_publisher,
        parse_prices,
        parse_reprints,
        parse_resources,
        parse_series,
        consolidate_reprints,  # must come after reprints & series
        parse_universes,
    )

    FROM_COMICBOX_PRE_TRANSFORM = (
        *XmlTransform.FROM_COMICBOX_PRE_TRANSFORM,
        unparse_age_rating,
        unparse_arcs,
        unparse_credits,
        unparse_identifiers,
        unparse_prices,
        unparse_publisher,
        unparse_resources,
        unparse_series,
        unparse_reprints,  # must come after series
        unparse_universes,
    )
