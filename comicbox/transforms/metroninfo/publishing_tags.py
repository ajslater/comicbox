"""Metron publishing tags transforms."""

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import IMPRINT_KEY, NAME_KEY, PUBLISHER_KEY
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.transforms.transform_map import KeyTransforms

NAME_TAG = "Name"


def _publisher_to_cb(source_data, metron_publisher):
    comicbox_publisher = {NAME_KEY: metron_publisher.get(NAME_TAG)}
    metron_id_attribute_to_cb(
        source_data, "publisher", metron_publisher, comicbox_publisher
    )
    return comicbox_publisher


def _publisher_from_cb(source_data, comicbox_publisher):
    metron_publisher = {}
    if publisher_name := comicbox_publisher.get(NAME_KEY):
        metron_publisher[NAME_TAG] = publisher_name
    metron_id_attribute_from_cb(source_data, metron_publisher, comicbox_publisher)
    return metron_publisher


def _imprint_to_cb(source_data, metron_imprint):
    comicbox_imprint = {}
    if imprint_name := get_cdata(metron_imprint):
        comicbox_imprint[NAME_KEY] = imprint_name
    metron_id_attribute_to_cb(source_data, "imprint", metron_imprint, comicbox_imprint)
    return comicbox_imprint


def _imprint_from_cb(source_data, comicbox_imprint):
    metron_imprint = {}
    if imprint_name := comicbox_imprint.get(NAME_KEY):
        metron_imprint["#text"] = imprint_name
    metron_id_attribute_from_cb(source_data, metron_imprint, comicbox_imprint)
    return metron_imprint


METRON_PUBLISHER_TRANSFORM = KeyTransforms(
    key_map={"Publisher": PUBLISHER_KEY},
    to_cb=_publisher_to_cb,
    from_cb=_publisher_from_cb,
)


METRON_IMPRINT_TRANSFORM = KeyTransforms(
    key_map={"Publisher.Imprint": IMPRINT_KEY},
    to_cb=_imprint_to_cb,
    from_cb=_imprint_from_cb,
)
