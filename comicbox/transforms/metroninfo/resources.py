"""MetronInfo.xml Transformer for nested tags."""

from logging import getLogger
from types import MappingProxyType

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import (
    ARCS_KEY,
    CHARACTERS_KEY,
    DESIGNATION_KEY,
    GENRES_KEY,
    LOCATIONS_KEY,
    NUMBER_KEY,
    PRICES_KEY,
    STORIES_KEY,
    TAGS_KEY,
    TEAMS_KEY,
    UNIVERSES_KEY,
)
from comicbox.schemas.metroninfo import COUNTRY_ATTR, DESIGNATION_TAG, NUMBER_TAG
from comicbox.transforms.metroninfo.identified_name import (
    identified_name_from_cb,
    identified_name_to_cb,
    identified_name_with_tag_from_cb,
    identified_name_with_tag_to_cb,
)
from comicbox.transforms.transform_map import KeyTransforms

LOG = getLogger(__name__)

_RESOURCES_KEY_MAP = MappingProxyType(
    {
        "Characters.Character": CHARACTERS_KEY,
        "Genres.Genre": GENRES_KEY,
        "Locations.Location": LOCATIONS_KEY,
        "Stories.Story": STORIES_KEY,
        "Tags.Tag": TAGS_KEY,
        "Teams.Team": TEAMS_KEY,
    }
)


def _resources_to_cb(source_data, metron_resources, nss_type):
    comicbox_resources = {}
    for metron_resource in metron_resources:
        name, comicbox_resource = identified_name_to_cb(
            source_data, metron_resource, nss_type
        )
        comicbox_resources[name] = comicbox_resource
    return comicbox_resources


def _resources_from_cb(source_data, comicbox_resources):
    metron_resources = []
    for name, comicbox_resource in comicbox_resources.items():
        metron_resource = identified_name_from_cb(source_data, name, comicbox_resource)
        metron_resources.append(metron_resource)
    return metron_resources


def _create_resource_transform(metron_key_path, cb_key):
    nss_type = metron_key_path.split(".")[1].lower()

    def to_cb(source_data, metron_resources):
        return _resources_to_cb(source_data, metron_resources, nss_type)

    return KeyTransforms(
        key_map={metron_key_path: cb_key}, to_cb=to_cb, from_cb=_resources_from_cb
    )


def _create_resorce_transforms():
    kts = []
    for metron_key_path, cb_key in _RESOURCES_KEY_MAP.items():
        kt = _create_resource_transform(metron_key_path, cb_key)
        kts.append(kt)
    return tuple(kts)


METRON_RESOURCES_TRANSFORMS = _create_resorce_transforms()

def _arcs_to_cb(source_data, metron_arcs):
    comicbox_arcs = {}
    for metron_arc in metron_arcs:
        name, comicbox_arc = identified_name_with_tag_to_cb(source_data, metron_arc, "arc")
        if not name:
            continue
        number = metron_arc.get(NUMBER_TAG)
        if number is not None:
            comicbox_arc[NUMBER_KEY] = number
        comicbox_arcs[name] = comicbox_arc
    return comicbox_arcs


def _arcs_from_cb(source_data, comicbox_arcs):
    metron_arcs = []
    for name, comicbox_arc in comicbox_arcs.items():
        metron_arc = identified_name_with_tag_from_cb(source_data, name, comicbox_arc)
        if number := comicbox_arc.get(NUMBER_KEY):
            metron_arc[NUMBER_TAG] = number
        metron_arcs.append(metron_arc)
    return metron_arcs


METRON_ARCS_TRANSFORM = KeyTransforms(
    key_map={"Arcs.Arc": ARCS_KEY}, to_cb=_arcs_to_cb, from_cb=_arcs_from_cb
)


def _prices_to_cb(_source_data, metron_prices):
    comicbox_prices = {}
    for metron_price in metron_prices:
        price = get_cdata(metron_price)
        country = metron_price.get(COUNTRY_ATTR, "")
        comicbox_prices[country] = price
    return comicbox_prices


def _prices_from_cb(_source_data, comicbox_prices):
    metron_prices = []
    for country, price in comicbox_prices.items():
        metron_price = {"#text": price}
        if country:
            metron_price[COUNTRY_ATTR] = country
        metron_prices.append(metron_price)
    return metron_prices


METRON_PRICES_TRANSFORM = KeyTransforms(
    key_map={"Prices.Price": PRICES_KEY}, to_cb=_prices_to_cb, from_cb=_prices_from_cb
)

def _universes_to_cb(source_data, metron_universes):
    comicbox_universes = {}
    for metron_universe in metron_universes:
        name, comicbox_universe = identified_name_with_tag_to_cb(
            source_data, metron_universe, "universe"
        )
        if not name:
            continue
        if designation := metron_universe.get(DESIGNATION_TAG):
            comicbox_universe[DESIGNATION_KEY] = designation
        comicbox_universes[name] = comicbox_universe
    return comicbox_universes


def _universes_from_cb(source_data, comicbox_universes):
    metron_universes = []
    for name, comicbox_universe in comicbox_universes.items():
        metron_universe = identified_name_with_tag_from_cb(source_data, name, comicbox_universe)
        if not metron_universe:
            continue
        if designation := comicbox_universe.get(DESIGNATION_KEY):
            metron_universe[DESIGNATION_TAG] = designation
        metron_universes.append(metron_universe)
    return metron_universes


METRON_UNIVERSES_TRANSFORM = KeyTransforms(
    key_map={"Universes.Universe": UNIVERSES_KEY},
    to_cb=_universes_to_cb,
    from_cb=_universes_from_cb,
)
