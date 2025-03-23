"""Transform metron identified names to comicbox identified objects."""

from collections.abc import Mapping
from enum import Enum

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.metroninfo import NAME_TAG
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)


def identified_name_to_cb(
    source_data: Mapping, metron_obj: Mapping | str, nss_type: str
) -> tuple[str, dict]:
    """Transform metron identified name to comicbox identified object."""
    comicbox_obj = {}
    if not (name := get_cdata(metron_obj)):
        return ("", comicbox_obj)
    if isinstance(name, Enum):
        name = name.value
    metron_id_attribute_to_cb(source_data, nss_type, metron_obj, comicbox_obj)
    return name, comicbox_obj


def identified_name_from_cb(
    source_data: Mapping, name: str | Enum, comicbox_obj: Mapping
) -> dict:
    """Transform comicbox identified object to a metron identified name."""
    metron_obj = {"#text": name}
    metron_id_attribute_from_cb(source_data, metron_obj, comicbox_obj)
    return metron_obj


def identified_name_with_tag_to_cb(
    source_data: Mapping, metron_obj: Mapping, nss_type: str
) -> tuple[str | Enum, dict]:
    """Transform metron identified name to comicbox identified object."""
    comicbox_obj = {}
    if not (name := get_cdata(metron_obj.get(NAME_TAG, ""))):
        return "", comicbox_obj
    metron_id_attribute_to_cb(source_data, nss_type, metron_obj, comicbox_obj)
    return name, comicbox_obj


def identified_name_with_tag_from_cb(
    source_data: Mapping, name: str | Enum, comicbox_obj: Mapping
) -> dict:
    """Transform comicbox ientified objects into metron identified objects with name tags."""
    metron_obj = {NAME_TAG: name}
    metron_id_attribute_from_cb(source_data, metron_obj, comicbox_obj)
    return metron_obj
