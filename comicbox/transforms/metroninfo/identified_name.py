"""Transform metron identified names to comicbox identified objects."""

from enum import Enum

from comicbox.fields.xml_fields import get_cdata
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)


def identified_name_to_cb(
    source_data: dict, metron_obj: dict | str, nss_type: str
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
    source_data: dict, name: str | Enum, comicbox_obj: dict
) -> dict:
    """Transform comicbox identified object to a metron identified name."""
    metron_obj = {"#text": name}
    metron_id_attribute_from_cb(source_data, metron_obj, comicbox_obj)
    return metron_obj
