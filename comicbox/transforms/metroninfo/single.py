"""MetronInfo.xml Transformer for single tags."""

from bidict import frozenbidict
from comicbox.merge import ADD_UNIQUE_MERGER
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
from comicbox.transforms.metroninfo.base import MetronInfoTransformBase


class MetronInfoTransformSingleTags(MetronInfoTransformBase):
    """MetronInfo Transformer for single tags."""

    SERIES_TAG_MAP = frozenbidict(
        {
            "Name": NAME_KEY,
            "SortName": SERIES_SORT_NAME_KEY,
            "StartYear": SERIES_START_YEAR_KEY,
            "VolumeCount": VOLUME_COUNT_KEY,
        }
    )
    SERIES_VOLUME_TAG = "Volume"
    SERIES_VOLUME_TAG_MAP = frozenbidict(
        {
            SERIES_VOLUME_TAG: VOLUME_NUMBER_KEY,
            "IssueCount": VOLUME_ISSUE_COUNT_KEY,
        }
    )
    GTIN_TAG = "GTIN"
    IMPRINT_TAG = "Imprint"
    MANGA_VOLUME_TAG = "MangaVolume"
    NAME_TAG = "Name"
    PUBLISHER_TAG = "Publisher"
    SERIES_TAG = "Series"
    SERIES_ALTERNATIVE_NAMES_TAG = "AlternativeNames"
    SERIES_ALTERNATIVE_NAME_TAG = "AlternativeName"
    SERIES_FORMAT_TAG = "Format"
    SERIES_LANG_ATTRIBUTE = "@lang"
    SERIES_REPRINTS_KEY = "series_reprints_tmp"

    # UTILITY
    ###########################################################################
    @staticmethod
    def _copy_tags(from_dict, to_dict, tag_dict):
        for from_key, to_key in tag_dict.items():
            if value := from_dict.get(from_key):
                to_dict[to_key] = value

    # PUBLISHER
    ###########################################################################
    @classmethod
    def _parse_imprint(cls, data, metron_publisher):
        metron_imprint = metron_publisher.get(cls.IMPRINT_TAG)
        if not metron_imprint:
            return
        imprint_name = get_cdata(metron_imprint)
        if not imprint_name:
            return
        imprint = {NAME_KEY: imprint_name}
        cls._parse_metron_id_attribute(data, "imprint", metron_imprint, imprint)
        if imprint_name:
            data[IMPRINT_KEY] = imprint

    def parse_publisher(self, data):
        """Parse Metron Publisher."""
        metron_publisher = data.pop(self.PUBLISHER_TAG, None)
        if not metron_publisher:
            return data
        publisher = {NAME_KEY: metron_publisher.get(self.NAME_TAG)}
        self._parse_metron_id_attribute(data, "publisher", metron_publisher, publisher)
        if publisher:
            data[PUBLISHER_KEY] = publisher

        self._parse_imprint(data, metron_publisher)
        return data

    def unparse_publisher(self, data):
        """Unparse Metron publisher."""
        publisher = data.pop(PUBLISHER_KEY, {})
        publisher_name = publisher.get(NAME_KEY)
        metron_publisher = {}
        if publisher_name:
            metron_publisher[self.NAME_TAG] = publisher_name
        self._unparse_metron_id_attribute(data, metron_publisher, publisher)
        imprint = data.pop(IMPRINT_KEY, {})
        metron_imprint = {}
        if imprint_name := imprint.get(NAME_KEY):
            metron_imprint["#text"] = imprint_name
        self._unparse_metron_id_attribute(data, metron_imprint, imprint)
        if metron_imprint:
            metron_publisher[self.IMPRINT_TAG] = metron_imprint
        if metron_publisher:
            data[self.PUBLISHER_TAG] = metron_publisher
        return data

    # SERIES
    ###########################################################################
    @classmethod
    def _parse_series_series_key(cls, data, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox series key."""
        series = {}

        cls._copy_tags(metron_series, series, cls.SERIES_TAG_MAP)
        cls._parse_metron_id_attribute(data, "series", metron_series, series)
        if series:
            update_dict[SERIES_KEY] = series

    @classmethod
    def _parse_series_volume_key(cls, metron_series, update_dict) -> None:
        """Parse metron series tags into comicbox volume key."""
        volume = {}

        cls._copy_tags(metron_series, volume, cls.SERIES_VOLUME_TAG_MAP)

        if number := metron_series.get(cls.SERIES_VOLUME_TAG):
            volume[NUMBER_KEY] = number

        if volume:
            update_dict[VOLUME_KEY] = volume

    @classmethod
    def _parse_series_alternative_names(cls, data, metron_series) -> dict:
        """Parse metron series alternative name tags into reprints."""
        alternative_names = metron_series.get(cls.SERIES_ALTERNATIVE_NAMES_TAG)
        if not alternative_names:
            return data
        alternative_names = alternative_names.get(cls.SERIES_ALTERNATIVE_NAME_TAG)
        if not alternative_names:
            return data
        reprints = []
        aliases = set()

        for an in alternative_names:
            alternative_name = get_cdata(an)
            if not alternative_name:
                continue
            aliases.add(alternative_name)
            reprint = {SERIES_KEY: {NAME_KEY: alternative_name}}
            # if alternative_name_id := an.get(ID_ATTRIBUTE):
            # to reprint identifier or main identifier?
            if alternative_name_lang := an.get(cls.SERIES_LANG_ATTRIBUTE):
                reprint[LANGUAGE_KEY] = alternative_name_lang
            reprints.append(reprint)

        if reprints:
            # consolidated later.
            data[cls.SERIES_REPRINTS_KEY] = reprints
        return data

    def parse_series(self, data):
        """Parse complex metron series into comicbox data."""
        metron_series = data.pop(self.SERIES_TAG, None)
        if not metron_series:
            return data
        update_dict = {}

        if language := metron_series.get(self.SERIES_LANG_ATTRIBUTE):
            update_dict[LANGUAGE_KEY] = language
        self._parse_series_series_key(data, metron_series, update_dict)
        self._parse_series_volume_key(metron_series, update_dict)
        if original_format := metron_series.get(self.SERIES_FORMAT_TAG):
            update_dict[ORIGINAL_FORMAT_KEY] = original_format.value
        data = self._parse_series_alternative_names(data, metron_series)

        if update_dict:
            ADD_UNIQUE_MERGER.merge(data, update_dict)

        return data

    def parse_manga_volume(self, data):
        """Parse the metron MangaVolume tag."""
        if manga_volume_name := data.pop(self.MANGA_VOLUME_TAG, None):
            volume = data.get(VOLUME_KEY, {})
            parts = manga_volume_name.split("-")
            if NUMBER_KEY not in volume:
                volume[NUMBER_KEY] = parts[0]
            if len(parts) > 1:
                volume[NUMBER_TO_KEY] = parts[1]
            data[VOLUME_KEY] = volume
        return data

    @classmethod
    def _unparse_series_alternative_names(cls, data, metron_series):
        """Unparse metron series alternative names from reprints."""
        # set dedupes
        alt_names: set[tuple[tuple[str, str], ...]] = set()
        if reprints := data.get(REPRINTS_KEY):
            for reprint in reprints:
                if series := reprint.get(SERIES_KEY):
                    alt_name: list[tuple[str, str]] = []
                    if series_name := series.get(NAME_KEY):
                        pair = ("#text", series_name)
                        alt_name.append(pair)
                    if series_lang := reprint.get(LANGUAGE_KEY):
                        pair = (cls.SERIES_LANG_ATTRIBUTE, series_lang)
                        alt_name.append(pair)
                    if alt_name:
                        alt_names.add(tuple(alt_name))
        if alt_names:
            alt_names_list: list[dict[str, str]] = [
                dict(alt_name) for alt_name in alt_names
            ]
            metron_series[cls.SERIES_ALTERNATIVE_NAMES_TAG] = {
                cls.SERIES_ALTERNATIVE_NAME_TAG: alt_names_list
            }

    def unparse_series(self, data):
        """Unparse the data into the complex metron series tag."""
        metron_series = {}
        if language := data.get(LANGUAGE_KEY):
            metron_series[self.SERIES_LANG_ATTRIBUTE] = language

        if series := data.get(SERIES_KEY):
            self._copy_tags(series, metron_series, self.SERIES_TAG_MAP.inverse)
            self._unparse_metron_id_attribute(data, metron_series, series)

        if volume := data.get(VOLUME_KEY):
            self._copy_tags(volume, metron_series, self.SERIES_VOLUME_TAG_MAP.inverse)
            number = volume.get(NUMBER_KEY)
            number_to = volume.get(NUMBER_TO_KEY)
            if number is not None and number_to is not None:
                data[self.MANGA_VOLUME_TAG] = f"{number}-{number_to}"

        if original_format := data.get(ORIGINAL_FORMAT_KEY):
            metron_series[self.SERIES_FORMAT_TAG] = original_format

        # Add series id
        self._unparse_series_alternative_names(data, metron_series)

        if metron_series:
            if self.SERIES_TAG not in data:
                data[self.SERIES_TAG] = {}
            ADD_UNIQUE_MERGER.merge(data[self.SERIES_TAG], metron_series)

        return data
