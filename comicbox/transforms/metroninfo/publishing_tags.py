"""Metron publishing tags transforms."""

from types import MappingProxyType

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import (
    IMPRINT_KEY,
    LANGUAGE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    NUMBER_TO_KEY,
    ORIGINAL_FORMAT_KEY,
    PUBLISHER_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    SERIES_SORT_NAME_KEY,
    SERIES_START_YEAR_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.transforms.metroninfo.identifier_attribute import (
    metron_id_attribute_from_cb,
    metron_id_attribute_to_cb,
)
from comicbox.transforms.transform_map import KeyTransforms

NAME_TAG = "Name"
VOLUME_KEY_PATH = "Series.Volume"
ALTERNATIVE_NAMES_KEY_PATH = "Series.AlternativeNames.AlternativeName"
LANG_ATTR = "@lang"
LANGUAGE_KEY_PATH = f"Series.{LANG_ATTR}"
FORMAT_KEY_PATH = "Series.Format"


SERIES_KEY_MAP = MappingProxyType(
    {
        f"Series.{LANG_ATTR}": LANGUAGE_KEY,
        "Series.Format": ORIGINAL_FORMAT_KEY,
        "Series.IssueCount": f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}",
        "Series.Name": f"{SERIES_KEY}.{NAME_KEY}",
        "Series.SortName": f"{SERIES_KEY}.{SERIES_SORT_NAME_KEY}",
        "Series.StartYear": f"{SERIES_KEY}.{SERIES_START_YEAR_KEY}",
        "Series.Volume": f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}",
        "Series.VolumeCount": f"{SERIES_KEY}.{VOLUME_COUNT_KEY}",
    }
)


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


METRON_PUBLISHER_TRANSFORM = KeyTransforms(
    key_map={"Publisher": PUBLISHER_KEY},
    to_cb=_publisher_to_cb,
    from_cb=_publisher_from_cb,
)


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


METRON_IMPRINT_TRANSFORM = KeyTransforms(
    key_map={"Publisher.Imprint": IMPRINT_KEY},
    to_cb=_imprint_to_cb,
    from_cb=_imprint_from_cb,
)


def _series_identifiers_to_cb(source_data, metron_series):
    comicbox_series = {}
    metron_id_attribute_to_cb(source_data, "series", metron_series, comicbox_series)
    return comicbox_series


def _series_identifiers_from_cb(source_data, comicbox_series):
    metron_series = {}
    metron_id_attribute_from_cb(source_data, metron_series, comicbox_series)
    return metron_series


METRON_SERIES_IDENTIFIERS_TRANSFORM = KeyTransforms(
    key_map={"Series": SERIES_KEY},
    to_cb=_series_identifiers_to_cb,
    from_cb=_series_identifiers_from_cb,
)


def _alternative_names_to_cb(source_data, metron_alternative_names):
    comicbox_reprints = []
    for an in metron_alternative_names:
        reprint = {}
        if alternative_name := get_cdata(an):
            reprint[SERIES_KEY] = {NAME_KEY: alternative_name}
        if alternative_name_lang := an.get(LANG_ATTR):
            reprint[LANGUAGE_KEY] = alternative_name_lang
        metron_id_attribute_to_cb(source_data, "reprint", an, reprint)
        if reprint:
            comicbox_reprints.append(reprint)
    return comicbox_reprints


def _alternative_names_from_cb(_source_data, comicbox_reprints):
    alt_names = []
    for reprint in comicbox_reprints:
        if reprint_series := reprint.get(SERIES_KEY):
            alt_name = {}
            if series_name := reprint_series.get(NAME_KEY):
                alt_name["#text"] = series_name
            if series_lang := reprint.get(LANGUAGE_KEY):
                alt_name[LANG_ATTR] = series_lang
            if alt_name:
                alt_names.append(alt_name)
    return alt_names


METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM = KeyTransforms(
    key_map={ALTERNATIVE_NAMES_KEY_PATH: REPRINTS_KEY},
    to_cb=_alternative_names_to_cb,
    from_cb=_alternative_names_from_cb,
)


def _manga_volume_to_cb(_source_data, metron_manga_volume):
    volume = {}
    parts = metron_manga_volume.split("-")
    if parts:
        if NUMBER_KEY not in volume:
            volume[NUMBER_KEY] = parts[0]
        if len(parts) > 1:
            volume[NUMBER_TO_KEY] = parts[1]
    return volume


def _manga_volume_from_cb(_source_data, comicbox_volume):
    parts = []
    from_vol = comicbox_volume.get(NUMBER_KEY)
    if from_vol is not None:
        parts.append(str(from_vol))
    to_vol = comicbox_volume.get(NUMBER_TO_KEY)
    if to_vol is not None:
        parts.append(str(to_vol))
    return "-".join(parts)


METRON_MANGA_VOLUME_TRANSFORM = KeyTransforms(
    key_map={"MangaVolume": VOLUME_KEY},
    to_cb=_manga_volume_to_cb,
    from_cb=_manga_volume_from_cb,
)
