"""Comictagger identifier transforms."""

from bidict import frozenbidict

from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_SOURCE,
    ID_KEY_KEY,
    ID_SOURCE_NAME_MAP,
    ID_SOURCE_VALUES,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
)
from comicbox.schemas.comicbox import (
    ID_SOURCE_KEY,
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    SERIES_KEY,
)
from comicbox.schemas.comictagger import DATA_ORIGIN_TAG, ISSUE_ID_TAG
from comicbox.transforms.identifiers import (
    PRIMARY_ID_SOURCE_KEYPATH,
    create_identifier_primary_source,
    identifiers_transform_from_cb,
    identifiers_transform_to_cb,
    urls_transform_from_cb,
    urls_transform_to_cb,
)
from comicbox.transforms.spec import MetaSpec

DATA_ORIGIN_NAME_KEYPATH = f"{DATA_ORIGIN_TAG}.name"


def _identifiers_primary_source_key_to_cb(data_origin):
    if (data_origin_id := data_origin.get("id")) and (
        id_source := ALIAS_ID_SOURCE_MAP.get(data_origin_id.lower(), DEFAULT_ID_SOURCE)
    ):
        ips = create_identifier_primary_source(id_source)
    else:
        ips = None
    return ips


_IDPS_KEY_MAP = frozenbidict({"data_origin": IDENTIFIER_PRIMARY_SOURCE_KEY})

COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB = MetaSpec(
    key_map=_IDPS_KEY_MAP.inverse, spec=_identifiers_primary_source_key_to_cb
)


def _identifiers_primary_source_key_from_cb(primary_source_key):
    data_origin = None
    if id_source := primary_source_key.get(ID_SOURCE_KEY):
        data_origin = {"id": id_source}
        if name := ID_SOURCE_NAME_MAP.get(id_source):
            data_origin["name"] = name
    return data_origin


COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_FROM_CB = MetaSpec(
    key_map=_IDPS_KEY_MAP, spec=_identifiers_primary_source_key_from_cb
)


def _get_id_source(data_origin_name):
    return ALIAS_ID_SOURCE_MAP.get(data_origin_name.lower(), DEFAULT_ID_SOURCE)


def _issue_id_to_cb(values):
    data_origin_name = values.get(DATA_ORIGIN_NAME_KEYPATH)
    id_source = _get_id_source(data_origin_name)
    issue_id = values.get(ISSUE_ID_TAG)
    identifier = create_identifier(id_source, issue_id)
    return {id_source: identifier}


COMICTAGGER_ISSUE_ID_TRANSFORM_TO_CB = MetaSpec(
    key_map={IDENTIFIERS_KEY: (ISSUE_ID_TAG, DATA_ORIGIN_NAME_KEYPATH)},
    spec=_issue_id_to_cb,
)


def _issue_id_from_cb(values):
    identifiers = values.get(IDENTIFIERS_KEY)
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH)
    for id_source in (primary_id_source, *ID_SOURCE_VALUES):
        if id_key := identifiers.get(id_source, {}).get(ID_KEY_KEY):
            return id_key
    return None


COMICTAGGER_ISSUE_ID_TRANSFORM_FROM_CB = MetaSpec(
    key_map={ISSUE_ID_TAG: (IDENTIFIERS_KEY, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_issue_id_from_cb,
)

SERIES_ID_TAG = "series_id"
SERIES_IDS_KEYPATH = f"{SERIES_KEY}.{IDENTIFIERS_KEY}"


def _series_id_to_cb(values):
    series_id = values.get(SERIES_ID_TAG)
    if not series_id:
        return None
    data_origin_name = values.get(DATA_ORIGIN_NAME_KEYPATH)
    id_source = _get_id_source(data_origin_name)
    identifier = create_identifier(id_source, series_id, id_type="series")
    return {id_source: identifier}


COMICTAGGER_SERIES_ID_TRANSFORM_TO_CB = MetaSpec(
    key_map={SERIES_IDS_KEYPATH: (SERIES_ID_TAG, DATA_ORIGIN_NAME_KEYPATH)},
    spec=_series_id_to_cb,
)


def _series_id_from_cb(values):
    series_identifiers = values.get(SERIES_IDS_KEYPATH)
    if not series_identifiers:
        return None
    primary_id_source = values.get(PRIMARY_ID_SOURCE_KEYPATH)
    for id_source in (primary_id_source, *ID_SOURCE_VALUES):
        if id_source and (
            id_key := series_identifiers.get(id_source, {}).get(ID_KEY_KEY)
        ):
            return id_key
    return None


COMICTAGGER_SERIES_ID_TRANSFORM_FROM_CB = MetaSpec(
    key_map={SERIES_ID_TAG: (SERIES_IDS_KEYPATH, PRIMARY_ID_SOURCE_KEYPATH)},
    spec=_series_id_from_cb,
)


COMICTAGGER_IDENTIFIERS_TRANSFORM_TO_CB = identifiers_transform_to_cb(
    "identifier", DEFAULT_ID_SOURCE
)
COMICTAGGER_IDENTIFIERS_TRANSFORM_FROM_CB = identifiers_transform_from_cb("identifier")

COMICTAGGER_URLS_TRANSFORM_TO_CB = urls_transform_to_cb("web_link")
COMICTAGGER_URLS_TRANSFORM_FROM_CB = urls_transform_from_cb("web_link")
