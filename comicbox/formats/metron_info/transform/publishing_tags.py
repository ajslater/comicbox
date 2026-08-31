"""Metron publishing tags transforms."""

from types import MappingProxyType
from typing import Any

from bidict import frozenbidict

from comicbox.formats.base.fields.xml_fields import get_cdata
from comicbox.formats.base.transforms.identifiers import PRIMARY_ID_SOURCE_KEYPATH
from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import (
    IDENTIFIERS_KEY,
    IMPRINT_KEY,
    LANGUAGE_KEY,
    MANGA_VOLUME_KEY,
    NAME_KEY,
    NUMBER_KEY,
    ORIGINAL_FORMAT_KEY,
    PUBLISHER_KEY,
    SERIES_KEY,
    SERIES_SORT_NAME_KEY,
    SERIES_START_YEAR_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.formats.metron_info.schema import (
    IMPRINT_TAG,
    LANG_ATTR,
    MANGA_VOLUME_TAG,
    NAME_TAG,
    PUBLISHER_TAG,
    SERIES_TAG,
    VOLUME_TAG,
)
from comicbox.formats.metron_info.transform.const import DEFAULT_ID_SOURCE_STR
from comicbox.formats.metron_info.transform.identifier_attribute import (
    ID_ATTRIBUTE,
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.formats.metron_info.transform.identifiers import SCOPE_PRIMARY_SOURCE

LANGUAGE_TAGPATH = f"{SERIES_TAG}.{LANG_ATTR}"
FORMAT_TAGPATH = f"{SERIES_TAG}.Format"
IMPRINT_TAGPATH = f"{PUBLISHER_TAG}.{IMPRINT_TAG}"
SERIES_ID_TAGPATH = f"{SERIES_TAG}.{ID_ATTRIBUTE}"
SERIES_IDENTIFIER_KEYPATH = f"{SERIES_KEY}.{IDENTIFIERS_KEY}"
SERIES_KEY_MAP_TO = frozenbidict(
    {
        LANGUAGE_KEY: LANGUAGE_TAGPATH,
        ORIGINAL_FORMAT_KEY: FORMAT_TAGPATH,
        f"{SERIES_KEY}.{NAME_KEY}": f"{SERIES_TAG}.Name",
        f"{SERIES_KEY}.{SERIES_SORT_NAME_KEY}": f"{SERIES_TAG}.SortName",
        f"{SERIES_KEY}.{SERIES_START_YEAR_KEY}": f"{SERIES_TAG}.StartYear",
        f"{SERIES_KEY}.{VOLUME_COUNT_KEY}": f"{SERIES_TAG}.VolumeCount",
    }
)
ISSUE_COUNT_TAGPATH = f"{SERIES_TAG}.IssueCount"
VOLUME_TAGPATH = f"{SERIES_TAG}.{VOLUME_TAG}"
SERIES_KEY_MAP_FROM = MappingProxyType(
    {
        **SERIES_KEY_MAP_TO.inverse,
        ISSUE_COUNT_TAGPATH: f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}",
        VOLUME_TAGPATH: f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}",
    }
)


def _publisher_to_cb(
    values: dict[str, Any],
) -> dict | None:
    metron_publisher = values.get(PUBLISHER_TAG)
    if not metron_publisher:
        return None
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE_STR)
    comicbox_publisher = {}
    if name := metron_publisher.get(NAME_TAG):
        comicbox_publisher[NAME_KEY] = name
    metron_id_attribute_to_cb(
        "publisher", metron_publisher, comicbox_publisher, primary_id_source
    )
    return comicbox_publisher


def _imprint_from_cb(values: dict[str, Any], primary_id_source: str) -> dict | None:
    comicbox_imprint = values.get(IMPRINT_KEY)
    if not comicbox_imprint:
        return None
    metron_imprint = {}
    if imprint_name := comicbox_imprint.get(NAME_KEY):
        metron_imprint["#text"] = imprint_name
    metron_id_attribute_from_cb(metron_imprint, comicbox_imprint, primary_id_source)
    return metron_imprint


def _publisher_from_cb(values: dict[str, Any]) -> dict:
    metron_publisher = {}
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE_STR)
    if comicbox_publisher := values.get(PUBLISHER_KEY):
        if publisher_name := comicbox_publisher.get(NAME_KEY):
            metron_publisher[NAME_TAG] = publisher_name
        metron_id_attribute_from_cb(
            metron_publisher, comicbox_publisher, primary_id_source
        )
    if metron_imprint := _imprint_from_cb(values, primary_id_source):
        metron_publisher[IMPRINT_TAG] = metron_imprint
    return metron_publisher


METRON_PUBLISHER_TRANSFORM_TO_CB = MetaSpec(
    key_map={PUBLISHER_KEY: (PUBLISHER_TAG, SCOPE_PRIMARY_SOURCE)},
    spec=_publisher_to_cb,
)

METRON_PUBLISHER_TRANSFORM_FROM_CB = MetaSpec(
    key_map={PUBLISHER_TAG: (PUBLISHER_KEY, IMPRINT_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_publisher_from_cb,
)


def _imprint_to_cb(values: dict[str, Any]) -> dict | None:
    metron_imprint = values.get(IMPRINT_TAGPATH)
    if not metron_imprint:
        return None
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE_STR)
    comicbox_imprint = {}
    if imprint_name := get_cdata(metron_imprint):
        comicbox_imprint[NAME_KEY] = imprint_name
    metron_id_attribute_to_cb(
        "imprint", metron_imprint, comicbox_imprint, primary_id_source
    )
    return comicbox_imprint


METRON_IMPRINT_TRANSFORM_TO_CB = MetaSpec(
    key_map={IMPRINT_KEY: (IMPRINT_TAGPATH, SCOPE_PRIMARY_SOURCE)},
    spec=_imprint_to_cb,
)

METRON_SERIES_TRANSFORM_TO_CB = MetaSpec(key_map=SERIES_KEY_MAP_TO)
METRON_SERIES_TRANSFORM_FROM_CB = MetaSpec(key_map=SERIES_KEY_MAP_FROM)


def _series_id_to_cb(values: dict[str, Any]) -> None:
    metron_series = values.get(SERIES_TAG)
    if not metron_series:
        return None
    primary_id_source = values.get(SCOPE_PRIMARY_SOURCE, DEFAULT_ID_SOURCE_STR)
    comicbox_series = {}
    metron_id_attribute_to_cb(
        "series", metron_series, comicbox_series, primary_id_source
    )
    return comicbox_series.get(IDENTIFIERS_KEY)


def _series_id_from_cb(values: dict[str, Any]) -> None:
    comicbox_series = values.get(SERIES_KEY)
    if not comicbox_series:
        return None
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH, DEFAULT_ID_SOURCE_STR)
    metron_series = {}
    metron_id_attribute_from_cb(metron_series, comicbox_series, primary_id_source)
    return metron_series.get(ID_ATTRIBUTE)


METRON_SERIES_IDENTIFIER_TRANSFORM_TO_CB = MetaSpec(
    # This goes down the series keypath, but it all ends up in the same big spec now.
    key_map={SERIES_IDENTIFIER_KEYPATH: (SERIES_TAG, SCOPE_PRIMARY_SOURCE)},
    spec=_series_id_to_cb,
)

METRON_SERIES_IDENTIFIER_TRANSFORM_FROM_CB = MetaSpec(
    key_map={SERIES_ID_TAGPATH: (SERIES_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_series_id_from_cb,
)


def _volume_to_cb(values: dict[str, Any]) -> dict | None:
    volume = {}
    metron_volume = values.get(VOLUME_TAGPATH)
    if metron_volume is not None:
        volume[NUMBER_KEY] = metron_volume
    if issue_count := values.get(ISSUE_COUNT_TAGPATH):
        volume[VOLUME_ISSUE_COUNT_KEY] = issue_count
    if not volume:
        volume = None
    return volume


METRON_VOLUME_TRANSFORM_TO_CB = MetaSpec(
    key_map={VOLUME_KEY: (VOLUME_TAGPATH, ISSUE_COUNT_TAGPATH)},
    spec=_volume_to_cb,
)

# MangaVolume is a free string in the MetronInfo schema, so comicbox stores it
# as one. It used to be split into volume.number and volume.number_to, and
# then rebuilt from them on every write — which stamped a MangaVolume onto
# western comics that never had one. It is now written only from the value a
# file actually supplied.
METRON_MANGA_VOLUME_TRANSFORM_TO_CB = MetaSpec(
    key_map={MANGA_VOLUME_KEY: MANGA_VOLUME_TAG}
)
METRON_MANGA_VOLUME_TRANSFORM_FROM_CB = MetaSpec(
    key_map={MANGA_VOLUME_TAG: MANGA_VOLUME_KEY}
)
