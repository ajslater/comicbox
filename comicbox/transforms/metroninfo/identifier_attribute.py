"""Metron ID attributes to comicbox identifiers transform."""

from collections.abc import Mapping

from loguru import logger

from comicbox.identifiers.identifiers import create_identifier
from comicbox.schemas.comicbox import ID_KEY_KEY, IDENTIFIERS_KEY
from comicbox.transforms.metroninfo.const import DEFAULT_ID_SOURCE

ID_ATTRIBUTE = "@id"


def metron_id_attribute_to_cb(
    id_type: str, metron_obj: Mapping | str, comicbox_obj: dict, id_source_str: str
) -> None:
    """Create a metron tag identifier from a metron identifier attribute."""
    try:
        if not (
            isinstance(metron_obj, Mapping) and (id_key := metron_obj.get(ID_ATTRIBUTE))
        ):
            return
        comicbox_identifier = create_identifier(
            id_source_str,
            id_key,
            id_type=id_type,
            default_id_source_str=DEFAULT_ID_SOURCE.value,
        )
        comicbox_obj[IDENTIFIERS_KEY] = {id_source_str: comicbox_identifier}
    except Exception as exc:
        logger.warning(f"Parsing metron tag identifier {id_type}:{metron_obj} - {exc}")


def metron_id_attribute_from_cb(
    metron_obj: dict, comicbox_obj: Mapping, primary_id_source_str: str
) -> None:
    """Crete a metron id attribute from comicbox identifier."""
    comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
    if not comicbox_identifiers:
        return
    for id_source_str, identifier in comicbox_identifiers.items():
        if (
            primary_id_source_str
            and id_source_str == primary_id_source_str
            and (id_key := identifier.get(ID_KEY_KEY))
        ):
            metron_obj[ID_ATTRIBUTE] = id_key
            break
