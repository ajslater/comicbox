"""MetronInfo.xml Transformer for nested tags."""

from collections.abc import Callable, Mapping
from enum import Enum
from types import MappingProxyType

from bidict import frozenbidict

from comicbox.fields.xml_fields import get_cdata
from comicbox.identifiers import DEFAULT_ID_SOURCE
from comicbox.schemas.comicbox import (
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
from comicbox.transforms.identifiers import PRIMARY_ID_SOURCE_KEYPATH
from comicbox.transforms.metroninfo.identified_name import (
    identified_name_from_cb,
    identified_name_to_cb,
    identified_name_with_tag_from_cb,
    identified_name_with_tag_to_cb,
)
from comicbox.transforms.metroninfo.identifiers import SCOPE_PRIMARY_SOURCE
from comicbox.transforms.spec import MetaSpec

ARC_KEYPATH = "Arcs.Arc"
UNIVERSES_KEYPATH = "Universes.Universe"
_PRICE_KEY_MAP = frozenbidict({"Prices.Price": PRICES_KEY})
_RESOURCES_KEY_MAP = MappingProxyType(
    {
        # Could be tuple, keys never used.
        "Characters.Character": CHARACTERS_KEY,
        "Genres.Genre": GENRES_KEY,
        "Locations.Location": LOCATIONS_KEY,
        "Stories.Story": STORIES_KEY,
        "Tags.Tag": TAGS_KEY,
        "Teams.Team": TEAMS_KEY,
    }
)


def metron_list_to_comicbox_dict(
    metron_objs: list[Mapping],
    id_type: str,
    primary_id_source: str,
    func: Callable[[Mapping | str, str, str], tuple[str | Enum, dict]],
) -> dict[str | Enum, dict]:
    """Transform metron lists into comicbox name dicts."""
    comicbox_objs = {}
    if metron_objs:
        for metron_obj in metron_objs:
            name, comicbox_obj = func(metron_obj, id_type, primary_id_source)
            if name:
                comicbox_objs[name] = comicbox_obj
    return comicbox_objs


def comicbox_dict_to_metron_list(
    comicbox_objs: Mapping,
    primary_id_source: str,
    func: Callable[[str | Enum, Mapping, str], dict],
) -> list[dict]:
    """Transform comicbox name dicts into metron lists."""
    metron_list = []
    if comicbox_objs:
        for name, comicbox_obj in comicbox_objs.items():
            if metron_obj := func(name, comicbox_obj, primary_id_source):
                metron_list.append(metron_obj)
    return metron_list


def _resources_to_cb(metron_resources, id_type, id_source):
    return metron_list_to_comicbox_dict(
        metron_resources, id_type, id_source, identified_name_to_cb
    )


def _resources_from_cb(cb_key, values):
    comicbox_resources = values.get(cb_key)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    return comicbox_dict_to_metron_list(
        comicbox_resources, primary_id_source, identified_name_from_cb
    )


def _create_resource_transform_to(metron_key_path, cb_key):
    id_type = metron_key_path.split(".")[1].lower()

    def to_cb(values):
        metron_resources = values.get(metron_key_path)
        id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
        return _resources_to_cb(metron_resources, id_type, id_source)

    return MetaSpec(
        key_map={cb_key: (metron_key_path, SCOPE_PRIMARY_SOURCE)}, spec=to_cb
    )


def _create_resource_transform_from(metron_key_path, cb_key):
    def from_cb(values):
        return _resources_from_cb(cb_key, values)

    return MetaSpec(
        key_map={metron_key_path: (cb_key, PRIMARY_ID_SOURCE_KEYPATH)},
        spec=from_cb,
    )


def _create_resource_transforms_to():
    return (
        _create_resource_transform_to(metron_key_path, cb_key)
        for metron_key_path, cb_key in _RESOURCES_KEY_MAP.items()
    )


def _create_resource_transforms_from():
    return (
        _create_resource_transform_from(metron_key_path, cb_key)
        for metron_key_path, cb_key in _RESOURCES_KEY_MAP.items()
    )


METRON_RESOURCES_TRANSFORMS_TO_CB = _create_resource_transforms_to()
METRON_RESOURCES_TRANSFORMS_FROM_CB = _create_resource_transforms_from()


def _arc_to_cb(
    metron_arc: Mapping | str, id_type: str, primary_id_source: str
) -> tuple[str | Enum, dict]:
    if not isinstance(metron_arc, Mapping):
        return "", {}

    name, comicbox_arc = identified_name_with_tag_to_cb(
        metron_arc, id_type, primary_id_source
    )
    if name:
        number = metron_arc.get(NUMBER_TAG)
        if number is not None:
            comicbox_arc[NUMBER_KEY] = number
    return name, comicbox_arc


def _arcs_to_cb(values):
    metron_arcs = values.get(ARC_KEYPATH, [])
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    return metron_list_to_comicbox_dict(
        metron_arcs, "arc", primary_id_source, _arc_to_cb
    )


def _arc_from_cb(name, comicbox_arc, primary_id_source):
    metron_arc = identified_name_with_tag_from_cb(name, comicbox_arc, primary_id_source)
    if number := comicbox_arc.get(NUMBER_KEY):
        metron_arc[NUMBER_TAG] = number
    return metron_arc


def _arcs_from_cb(values):
    comicbox_arcs = values.get(ARCS_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    return comicbox_dict_to_metron_list(comicbox_arcs, primary_id_source, _arc_from_cb)


METRON_ARCS_TRANSFORM_TO_CB = MetaSpec(
    key_map={ARCS_KEY: (ARC_KEYPATH, SCOPE_PRIMARY_SOURCE)},
    spec=_arcs_to_cb,
)

METRON_ARCS_TRANSFORM_FROM_CB = MetaSpec(
    key_map={"Arcs.Arc": (ARCS_KEY, PRIMARY_ID_SOURCE_KEYPATH)}, spec=_arcs_from_cb
)


def _prices_to_cb(metron_prices):
    comicbox_prices = {}
    for metron_price in metron_prices:
        price = get_cdata(metron_price)
        country = metron_price.get(COUNTRY_ATTR, "")
        comicbox_prices[country] = price
    return comicbox_prices


def _prices_from_cb(comicbox_prices):
    metron_prices = []
    for country, price in comicbox_prices.items():
        metron_price = {"#text": price}
        if country:
            metron_price[COUNTRY_ATTR] = country
        metron_prices.append(metron_price)
    return metron_prices


METRON_PRICES_TRANSFORM_TO_CB = MetaSpec(
    key_map=_PRICE_KEY_MAP.inverse,
    spec=_prices_to_cb,
)
METRON_PRICES_TRANSFORM_FROM_CB = MetaSpec(key_map=_PRICE_KEY_MAP, spec=_prices_from_cb)


def _universe_to_cb(metron_universe, id_type, primary_id_source):
    if not isinstance(metron_universe, Mapping):
        return "", {}
    name, comicbox_universe = identified_name_with_tag_to_cb(
        metron_universe, id_type, primary_id_source
    )
    if name and (designation := metron_universe.get(DESIGNATION_TAG)):
        comicbox_universe[DESIGNATION_KEY] = designation
    return name, comicbox_universe


def _universes_to_cb(values):
    metron_universes = values.get(UNIVERSES_KEYPATH)
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE)
    return metron_list_to_comicbox_dict(
        metron_universes, "universe", primary_id_source, _universe_to_cb
    )


def _universe_from_cb(name, comicbox_universe, primary_id_source):
    metron_universe = identified_name_with_tag_from_cb(
        name, comicbox_universe, primary_id_source
    )
    if metron_universe and (designation := comicbox_universe.get(DESIGNATION_KEY)):
        metron_universe[DESIGNATION_TAG] = designation
    return metron_universe


def _universes_from_cb(values):
    comicbox_universes = values.get(UNIVERSES_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE)
    return comicbox_dict_to_metron_list(
        comicbox_universes, primary_id_source, _universe_from_cb
    )


METRON_UNIVERSES_TRANSFORM_TO_CB = MetaSpec(
    key_map={UNIVERSES_KEY: (UNIVERSES_KEYPATH, SCOPE_PRIMARY_SOURCE)},
    spec=_universes_to_cb,
)
METRON_UNIVERSES_TRANSFORM_FROM_CB = MetaSpec(
    key_map={"Universes.Universe": (UNIVERSES_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_universes_from_cb,
)
