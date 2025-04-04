"""Comictagger identifier transforms."""

from bidict import frozenbidict

from comicbox.identifiers import (
    COMICVINE_NID,
    NID_ORIGIN_MAP,
    NSS_KEY,
    create_identifier,
)
from comicbox.schemas.comicbox import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    NID_KEY,
    SERIES_KEY,
)
from comicbox.transforms.identifiers import (
    PRIMARY_NID_KEYPATH,
    create_identifier_primary_source,
    identifiers_transform_from_cb,
    identifiers_transform_to_cb,
    urls_transform_from_cb,
    urls_transform_to_cb,
)
from comicbox.transforms.spec import MetaSpec
from comicbox.urns import IDENTIFIER_URN_NIDS, IDENTIFIER_URN_NIDS_REVERSE_MAP

DEFAULT_NID = COMICVINE_NID
DATA_ORIGIN_NAME_KEYPATH = "data_origin.name"
ISSUE_ID_TAG = "issue_id"


def _identifiers_primary_source_key_to_cb(data_origin):
    if (data_origin_id := data_origin.get("id")) and (
        nid := IDENTIFIER_URN_NIDS_REVERSE_MAP.get(data_origin_id.lower(), DEFAULT_NID)
    ):
        ips = create_identifier_primary_source(nid)
    else:
        ips = None
    return ips


_IDPS_KEY_MAP = frozenbidict({"data_origin": IDENTIFIER_PRIMARY_SOURCE_KEY})

COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_TO_CB = MetaSpec(
    key_map=_IDPS_KEY_MAP.inverse, spec=_identifiers_primary_source_key_to_cb
)


def _identifiers_primary_source_key_from_cb(primary_source_key):
    data_origin = None
    if nid := primary_source_key.get(NID_KEY):
        data_origin = {"id": nid}
        if name := NID_ORIGIN_MAP.get(nid):
            data_origin["name"] = name
    return data_origin


COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM_FROM_CB = MetaSpec(
    key_map=_IDPS_KEY_MAP, spec=_identifiers_primary_source_key_from_cb
)


def _get_nid(data_origin_name):
    return IDENTIFIER_URN_NIDS_REVERSE_MAP.get(data_origin_name.lower(), DEFAULT_NID)


def _issue_id_to_cb(values):
    data_origin_name = values.get(DATA_ORIGIN_NAME_KEYPATH)
    nid = _get_nid(data_origin_name)
    issue_id = values.get(ISSUE_ID_TAG)
    identifier = create_identifier(nid, issue_id)
    return {nid: identifier}


COMICTAGGER_ISSUE_ID_TRANSFORM_TO_CB = MetaSpec(
    key_map={IDENTIFIERS_KEY: (ISSUE_ID_TAG, DATA_ORIGIN_NAME_KEYPATH)},
    spec=_issue_id_to_cb,
)


def _issue_id_from_cb(values):
    identifiers = values.get(IDENTIFIERS_KEY)
    primary_nid = values.get(PRIMARY_NID_KEYPATH)
    for nid in (primary_nid, *IDENTIFIER_URN_NIDS):
        if nss := identifiers.get(nid, {}).get(NSS_KEY):
            return nss
    return None


COMICTAGGER_ISSUE_ID_TRANSFORM_FROM_CB = MetaSpec(
    key_map={ISSUE_ID_TAG: (IDENTIFIERS_KEY, PRIMARY_NID_KEYPATH)},
    spec=_issue_id_from_cb,
)

SERIES_ID_TAG = "series_id"
SERIES_IDS_KEYPATH = f"{SERIES_KEY}.{IDENTIFIERS_KEY}"


def _series_id_to_cb(values):
    series_id = values.get(SERIES_ID_TAG)
    if not series_id:
        return None
    data_origin_name = values.get(DATA_ORIGIN_NAME_KEYPATH)
    nid = _get_nid(data_origin_name)
    identifier = create_identifier(nid, series_id)
    return {IDENTIFIERS_KEY: {nid: identifier}}


COMICTAGGER_SERIES_ID_TRANSFORM_TO_CB = MetaSpec(
    key_map={SERIES_IDS_KEYPATH: (SERIES_ID_TAG, DATA_ORIGIN_NAME_KEYPATH)},
    spec=_series_id_to_cb,
)


def _series_id_from_cb(values):
    series_identifiers = values.get(SERIES_IDS_KEYPATH)
    if not series_identifiers:
        return None
    primary_nid = values.get(PRIMARY_NID_KEYPATH)
    for nid in (primary_nid, *IDENTIFIER_URN_NIDS):
        if nid and (nss := series_identifiers.get(nid, {}).get(NSS_KEY)):
            return nss
    return None


COMICTAGGER_SERIES_ID_TRANSFORM_FROM_CB = MetaSpec(
    key_map={SERIES_ID_TAG: (SERIES_IDS_KEYPATH, PRIMARY_NID_KEYPATH)},
    spec=_series_id_from_cb,
)


COMICTAGGER_IDENTIFIERS_TRANSFORM_TO_CB = identifiers_transform_to_cb(
    "identifier", DEFAULT_NID
)
COMICTAGGER_IDENTIFIERS_TRANSFORM_FROM_CB = identifiers_transform_from_cb("identifier")

COMICTAGGER_URLS_TRANSFORM_TO_CB = urls_transform_to_cb("web_link")
COMICTAGGER_URLS_TRANSFORM_FROM_CB = urls_transform_from_cb("web_link")
