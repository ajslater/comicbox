"""Comictagger identifier transforms."""

from glom import glom

from comicbox.identifiers import (
    COMICVINE_NID,
    NID_ORIGIN_MAP,
    NSS_KEY,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    NID_KEY,
    SERIES_KEY,
)
from comicbox.transforms.identifiers import (
    create_identifier_primary_source,
    identifiers_transform,
    urls_transform,
)
from comicbox.transforms.transform_map import KeyTransforms
from comicbox.urns import IDENTIFIER_URN_NIDS, IDENTIFIER_URN_NIDS_REVERSE_MAP

DEFAULT_NID = COMICVINE_NID
DATA_ORIGIN_NAME_KEY_PATH = "data_origin.name"
PRIMARY_NID_KEY_PATH = f"{IDENTIFIER_PRIMARY_SOURCE_KEY}.{NID_KEY}"


def _identifiers_primary_source_key_to_cb(_source_data, data_origin):
    if (data_origin_id := data_origin.get("id")) and (
        nid := IDENTIFIER_URN_NIDS_REVERSE_MAP.get(data_origin_id.lower(), DEFAULT_NID)
    ):
        ips = create_identifier_primary_source(nid)
    else:
        ips = None
    return ips


def _identifiers_primary_source_key_from_cb(_source_data, primary_source_key):
    data_origin = None
    if nid := primary_source_key.get(NID_KEY):
        data_origin = {"id": nid}
        if name := NID_ORIGIN_MAP.get(nid):
            data_origin["name"] = name
    return data_origin


COMICTAGGER_IDENTIFIER_PRIMARY_SOURCE_KEY_TRANSFORM = KeyTransforms(
    key_map={"data_origin": IDENTIFIER_PRIMARY_SOURCE_KEY},
    to_cb=_identifiers_primary_source_key_to_cb,
    from_cb=_identifiers_primary_source_key_from_cb,
)


def _get_nid(source_data):
    data_origin_name = glom(source_data, DATA_ORIGIN_NAME_KEY_PATH, default="")
    return IDENTIFIER_URN_NIDS_REVERSE_MAP.get(data_origin_name.lower(), DEFAULT_NID)


def _issue_id_to_cb(source_data, issue_id):
    nid = _get_nid(source_data)
    identifier = create_identifier(nid, issue_id)
    return {nid: identifier}


def _issue_id_from_cb(source_data, identifiers):
    primary_nid = glom(source_data, PRIMARY_NID_KEY_PATH, default="")
    for nid in (primary_nid, *IDENTIFIER_URN_NIDS):
        if nss := identifiers.get(nid, {}).get(NSS_KEY):
            return nss
    return None


COMICTAGGER_ISSUE_ID_TRANSFORM = KeyTransforms(
    key_map={"issue_id": IDENTIFIERS_KEY},
    to_cb=_issue_id_to_cb,
    from_cb=_issue_id_from_cb,
)


def _series_id_to_cb(source_data, series_id):
    nid = _get_nid(source_data)
    identifier = create_identifier(nid, series_id)
    return {IDENTIFIERS_KEY: {nid: identifier}}


def _series_id_from_cb(source_data, series_identifiers):
    primary_nid = glom(source_data, PRIMARY_NID_KEY_PATH, default="")
    for nid in (primary_nid, *IDENTIFIER_URN_NIDS):
        if nss := series_identifiers.get(nid, {}).get(NSS_KEY):
            return nss
    return None


SERIES_IDS_KEY_PATH = f"{SERIES_KEY}.{IDENTIFIERS_KEY}"
COMICTAGGER_SERIES_ID_TRANSFORM = KeyTransforms(
    key_map={"series_id": SERIES_IDS_KEY_PATH},
    to_cb=_series_id_to_cb,
    from_cb=_series_id_from_cb,
)

COMICTAGGER_IDENTIFIERS_TRANSFORM = identifiers_transform("identifier", DEFAULT_NID)
COMICTAGGER_URLS_TRANSFORM = urls_transform("web_link")
