"""MetronInfo.xml Transformer for nested tags."""

from collections.abc import Callable
from decimal import Decimal
from enum import Enum
from logging import getLogger
from types import MappingProxyType
from typing import Any

from bidict import frozenbidict

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import (
    CHARACTERS_KEY,
    CREDITS_KEY,
    DESIGNATION_KEY,
    GENRES_KEY,
    IDENTIFIERS_KEY,
    LOCATIONS_KEY,
    NUMBER_KEY,
    PRICES_KEY,
    REPRINTS_KEY,
    ROLES_KEY,
    STORIES_KEY,
    STORY_ARCS_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
)
from comicbox.schemas.identifier import URL_KEY
from comicbox.transforms.metroninfo.single import MetronInfoTransformSingleTags

LOG = getLogger(__name__)


class MetronInfoTransformNestedTags(MetronInfoTransformSingleTags):
    """MetronInfo Transformer for nested tags."""

    DESIGNATION_TAG = "Designation"
    UNIVERSE_TAG_MAP = frozenbidict({DESIGNATION_TAG: DESIGNATION_KEY})
    ARCS_TAG = "Arcs"
    ARC_NAME_TAG = "Name"
    ARC_NUMBER_TAG = "Number"
    CHARACTERS_TAG = "Characters"
    COUNTRY_ATTRIBUTE = "@country"
    GENRES_TAG = "Genres"
    LOCATIONS_TAG = "Locations"
    PRICES_TAG = "Prices"
    PRICE_TAG = "Price"
    REPRINTS_TAG = "Reprints"
    STORIES_TAG = "Stories"
    STORY_TAG = "Story"
    TEAMS_TAG = "Teams"
    TAGS_TAG = "Tags"
    UNIVERSES_TAG = "Universes"
    UNIVERSE_TAG = "Universe"
    URLS_TAG = "URLs"
    URL_TAG = "URL"
    IDS_TAG = "IDS"
    ID_TAG = "ID"
    IDENTIFIERS_TAG = IDS_TAG
    CREDITS_TAG = "Credits"
    ROLES_TAG = "Roles"
    PRIMARY_ATTRIBUTE = "@primary"
    SOURCE_ATTRIBUTE = "@source"
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

    # NESTED TAGS
    ###########################################################################
    @classmethod
    def _hoist_metron_tag(cls, base_obj: dict, tag: str):
        metron_objs = base_obj.pop(tag, None)
        if not metron_objs:
            return None
        single_tag = cls._IRREGULAR_SINGLE_TAGS.get(tag, tag[:-1])
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
            key = cls._NESTED_METRON_RESOURCE_TAGS.inverse[tag]
            base_obj[key] = comicbox_objs
        return base_obj

    @classmethod
    def _lower_metron_tag(cls, base_obj: dict, key: str, value) -> dict:
        if value in EMPTY_VALUES:
            return base_obj
        tag = cls._NESTED_METRON_RESOURCE_TAGS[key]
        single_tag = cls._IRREGULAR_SINGLE_TAGS.get(tag, tag[:-1])
        base_obj[tag] = {single_tag: value}
        return base_obj

    @classmethod
    def _unparse_metron_tag(
        cls,
        base_obj: dict,
        key: str,
        unparse_method: Callable[[dict, str, Any], dict | list],
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
                if isinstance(metron_obj, list):
                    # Expand one metron obj into many
                    metron_objs += metron_obj
                else:
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

    # RESOURCES
    ###########################################################################
    def parse_resources(self, data: dict) -> dict:
        """Parse Metron Resources."""
        for key, nss_type in self._METRON_RESOURCES.items():
            tag = self._NESTED_METRON_RESOURCE_TAGS[key]
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
        for key in self._METRON_RESOURCES:
            data = self._unparse_metron_tag(data, key, self._unparse_identified_name)
        return data

    # ARCS
    ###########################################################################
    @classmethod
    def _parse_arc(cls, data, metron_arc) -> tuple[str, dict]:
        """Parse one metron Arc."""
        comicbox_story_arc = {}
        if not (name := metron_arc.get(cls.ARC_NAME_TAG, "")):
            return (name, comicbox_story_arc)
        number = metron_arc.get(cls.ARC_NUMBER_TAG)
        if number is not None:
            comicbox_story_arc[NUMBER_KEY] = number
        cls._parse_metron_id_attribute(
            data, "story_arc", metron_arc, comicbox_story_arc
        )
        return name, comicbox_story_arc

    def parse_arcs(self, data):
        """Convert metron arcs list to story arcs map."""
        return self._parse_metron_tag(data, self.ARCS_TAG, self._parse_arc)

    @classmethod
    def _unparse_arc(cls, data, name, comicbox_story_arc: dict) -> dict:
        """Unparse one metron Arc."""
        metron_arc = {cls.ARC_NAME_TAG: name}
        number = comicbox_story_arc.get(NUMBER_KEY)
        if number is not None:
            metron_arc[cls.ARC_NUMBER_TAG] = number
        cls._unparse_metron_id_attribute(data, comicbox_story_arc, metron_arc)
        return metron_arc

    def unparse_arcs(self, data):
        """Convert story arc dict to metron arcs list."""
        return self._unparse_metron_tag(data, STORY_ARCS_KEY, self._unparse_arc)

    # PRICES
    ###########################################################################
    @classmethod
    def _parse_price(cls, _data, metron_price) -> tuple[str, dict]:
        """Parse a metron Price."""
        price = get_cdata(metron_price)
        if price is None:
            return "", {}
        country = metron_price.get(cls.COUNTRY_ATTRIBUTE, "")
        # TODO allow empty countries later
        return country, price

    def parse_prices(self, data: dict) -> dict:
        """Parse prices."""
        return self._parse_metron_tag(data, self.PRICES_TAG, self._parse_price)

    @classmethod
    def _unparse_price(cls, _data, country, price) -> dict:
        """Unparse a metron Price."""
        if price is None:
            return {}
        metron_price = {
            "#text": str(Decimal(price).quantize(Decimal("0.01"))),
        }
        if country:
            metron_price[cls.COUNTRY_ATTRIBUTE] = country
        return metron_price

    def unparse_prices(self, data: dict) -> dict:
        """Unparse Prices."""
        return self._unparse_metron_tag(data, PRICES_KEY, self._unparse_price)

    # UNIVERSES
    ###########################################################################
    @classmethod
    def _parse_universe(cls, data: dict, metron_universe) -> tuple[str, dict]:
        """Parse metron Universe."""
        name = metron_universe.get(cls.NAME_TAG, "")
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
        return self._parse_metron_tag(data, self.UNIVERSES_TAG, self._parse_universe)

    @classmethod
    def _unparse_universe(cls, data: dict, name: str, comicbox_universe) -> dict:
        """Unparse metron Universe."""
        if not name:
            return {}
        metron_universe = {cls.NAME_TAG: name}
        for tag, key in cls.UNIVERSE_TAG_MAP.items():
            if value := comicbox_universe.get(key):
                metron_universe[tag] = value
        cls._unparse_metron_id_attribute(data, metron_universe, comicbox_universe)
        return metron_universe

    def unparse_universes(self, data: dict) -> dict:
        """Unparse Universes."""
        return self._unparse_metron_tag(data, UNIVERSES_KEY, self._unparse_universe)
