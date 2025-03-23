"""MetronInfo.xml Transformer for nested tags."""

from collections.abc import Callable, Mapping
from enum import Enum
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


def metron_list_to_comicbox_dict(
    source_data: Mapping,
    metron_objs: list[Mapping],
    nss_type: str,
    func: Callable[[Mapping, Mapping | str, str], tuple[str | Enum, dict]],
) -> dict[str | Enum, dict]:
    """Transform metron lists into comicbox name dicts."""
    comicbox_objs = {}
    for metron_obj in metron_objs:
        name, comicbox_obj = func(source_data, metron_obj, nss_type)
        if name:
            comicbox_objs[name] = comicbox_obj
    return comicbox_objs


def comicbox_dict_to_metron_list(
    source_data: Mapping,
    comicbox_objs: Mapping,
    func: Callable[[Mapping, str | Enum, Mapping], dict],
) -> list[dict]:
    """Transform comicbox name dicts into metron lists."""
    metron_list = []
    for name, comicbox_obj in comicbox_objs.items():
        metron_obj = func(source_data, name, comicbox_obj)
        if metron_obj:
            metron_list.append(metron_obj)
    return metron_list


def _resources_to_cb(source_data, metron_resources, nss_type):
    return metron_list_to_comicbox_dict(
        source_data, metron_resources, nss_type, identified_name_to_cb
    )


def _resources_from_cb(source_data, comicbox_resources):
    return comicbox_dict_to_metron_list(
        source_data, comicbox_resources, identified_name_from_cb
    )


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


def _arc_to_cb(source_data, metron_arc, nss_type):
    name, comicbox_arc = identified_name_with_tag_to_cb(
        source_data, metron_arc, nss_type
    )
    if name:
        number = metron_arc.get(NUMBER_TAG)
        if number is not None:
            comicbox_arc[NUMBER_KEY] = number
    return name, comicbox_arc


def _arcs_to_cb(source_data, metron_arcs):
    return metron_list_to_comicbox_dict(source_data, metron_arcs, "arc", _arc_to_cb)


def _arc_from_cb(source_data, name, comicbox_arc):
    metron_arc = identified_name_with_tag_from_cb(source_data, name, comicbox_arc)
    if number := comicbox_arc.get(NUMBER_KEY):
        metron_arc[NUMBER_TAG] = number
    return metron_arc


def _arcs_from_cb(source_data, comicbox_arcs):
    return comicbox_dict_to_metron_list(source_data, comicbox_arcs, _arc_from_cb)


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


def _universe_to_cb(source_data, metron_universe, nss_type):
    name, comicbox_universe = identified_name_with_tag_to_cb(
        source_data, metron_universe, nss_type
    )
    if name and (designation := metron_universe.get(DESIGNATION_TAG)):
        comicbox_universe[DESIGNATION_KEY] = designation
    return name, comicbox_universe


def _universes_to_cb(source_data, metron_universes):
    return metron_list_to_comicbox_dict(
        source_data, metron_universes, "universe", _universe_to_cb
    )


def _universe_from_cb(source_data, name, comicbox_universe):
    metron_universe = identified_name_with_tag_from_cb(
        source_data, name, comicbox_universe
    )
    if metron_universe and (designation := comicbox_universe.get(DESIGNATION_KEY)):
        metron_universe[DESIGNATION_TAG] = designation
    return metron_universe


def _universes_from_cb(source_data, comicbox_universes):
    return comicbox_dict_to_metron_list(
        source_data, comicbox_universes, _universe_from_cb
    )


METRON_UNIVERSES_TRANSFORM = KeyTransforms(
    key_map={"Universes.Universe": UNIVERSES_KEY},
    to_cb=_universes_to_cb,
    from_cb=_universes_from_cb,
)
