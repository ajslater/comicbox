"""Metron ID attributes to comicbox identifiers transform."""

from collections.abc import Mapping

from loguru import logger

from comicbox.identifiers.identifiers import create_identifier
from comicbox.schemas.comicbox import IDENTIFIERS_KEY
from comicbox.transforms.metroninfo.const import DEFAULT_ID_SOURCE

ID_ATTRIBUTE = "@id"


def metron_id_attribute_to_cb(
    id_type: str, metron_obj: Mapping | str, comicbox_obj: dict, id_source: str
) -> None:
    """Create a metron tag identifier from a metron identifier attribute."""
    try:
        if not (
            isinstance(metron_obj, Mapping) and (id_key := metron_obj.get(ID_ATTRIBUTE))
        ):
            return
        comicbox_identifier = create_identifier(
            id_source, id_key, id_type=id_type, default_id_source=DEFAULT_ID_SOURCE
        )
        comicbox_obj[IDENTIFIERS_KEY] = {id_source: comicbox_identifier}
    except Exception as exc:
        logger.warning(f"Parsing metron tag identifier {id_type}:{metron_obj} - {exc}")


def metron_id_attribute_from_cb(
    metron_obj: dict, comicbox_obj: Mapping, primary_id_source: str
) -> None:
    """Crete a metron id attribute from comicbox identifier."""
    comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
    if not comicbox_identifiers:
        return
    for id_source, identifier in comicbox_identifiers.items():
        if (
            primary_id_source
            and id_source == primary_id_source
            and (id_key := identifier.get("id_key"))
        ):
            metron_obj[ID_ATTRIBUTE] = id_key
            break
