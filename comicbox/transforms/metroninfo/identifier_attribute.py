"""Metron ID attributes to comicbox identifiers transform."""

from collections.abc import Mapping
from logging import getLogger

from comicbox.identifiers import METRON_NID, create_identifier
from comicbox.schemas.comicbox_mixin import IDENTIFIERS_KEY
from comicbox.transforms.metroninfo.identifiers import get_primary_source_nid

ID_ATTRIBUTE = "@id"
LOG = getLogger(__name__)


def metron_id_attribute_to_cb(
    source_data: Mapping, nss_type: str, metron_obj: Mapping | str, comicbox_obj: dict
) -> None:
    """Create a metron tag identifier from a metron identifier attribute."""
    try:
        if not (
            isinstance(metron_obj, Mapping) and (nss := metron_obj.get(ID_ATTRIBUTE))
        ):
            return
        nid = get_primary_source_nid(source_data, METRON_NID)
        comicbox_identifier = create_identifier(nid, nss, nss_type=nss_type)
        comicbox_obj[IDENTIFIERS_KEY] = {nid: comicbox_identifier}
    except Exception as exc:
        LOG.warning(f"Parsing metron tag identifier {nss_type}:{metron_obj} - {exc}")


def metron_id_attribute_from_cb(
    source_data: Mapping, metron_obj: dict, comicbox_obj: Mapping
) -> None:
    """Crete a metron id attribute from comicbox identifier."""
    comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
    if not comicbox_identifiers:
        return
    primary_nid = get_primary_source_nid(source_data, METRON_NID)
    for nid, identifier in comicbox_identifiers.items():
        if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
            metron_obj[ID_ATTRIBUTE] = nss
            break
