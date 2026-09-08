"""Metron ID attributes to comicbox identifiers transform."""

from collections.abc import Mapping

from loguru import logger

from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY
from comicbox.formats.metron_info.transform.const import DEFAULT_ID_SOURCE_STR
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_KEY_KEY
from comicbox.identifiers.identifiers import create_identifier

ID_ATTRIBUTE = "@id"


def metron_id_attribute_to_cb(
    id_type: str,
    metron_obj: Mapping | str,
    comicbox_obj: dict,
    id_source_str: str,
    *,
    implied: bool = True,
) -> None:
    """
    Create a metron tag identifier from a metron identifier attribute.

    The attribute names no type of its own, so ``id_type`` is the type the
    tag it hangs on means. Usually that tag IS the thing the id names, and
    the type is left implied. ``implied=False`` is for a tag that is a name
    rather than the thing: an AlternativeName is not a series, so nothing
    about where its id sits says the id names one, and the type has to be
    stated the way a top level id states a type that isn't an issue.
    """
    try:
        if not (
            isinstance(metron_obj, Mapping) and (id_key := metron_obj.get(ID_ATTRIBUTE))
        ):
            return
        comicbox_identifier = create_identifier(
            id_source_str,
            # Mapping.get is untyped here; metron @id attributes arrive as
            # str from xmltodict but int from API dicts — coerce.
            str(id_key),
            id_type=id_type,
            positional_id_type=id_type if implied else DEFAULT_ID_TYPE,
            default_id_source_str=DEFAULT_ID_SOURCE_STR,
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
