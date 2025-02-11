"""Nested Publishing Tags."""

from comicbox.schemas.comicbox_mixin import (
    IMPRINT_KEY,
    NAME_KEY,
    PUBLISHER_KEY,
    SERIES_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)


class NestedPublishingTagsMixin:
    """Nested Publishing Tags."""

    PUBLISHER_TAG = ""
    IMPRINT_TAG = ""
    SERIES_TAG = ""
    VOLUME_COUNT_TAG = ""
    VOLUME_TAG = ""
    ISSUE_COUNT_TAG = ""

    def parse_series(self, data):
        """Parse Series."""
        series_name = data.get(self.SERIES_TAG)
        volume_count = data.get(self.VOLUME_COUNT_TAG)
        if series_name or volume_count:
            data[SERIES_KEY] = {}
            if series_name:
                data[SERIES_KEY][NAME_KEY] = series_name
            if volume_count:
                data[SERIES_KEY][VOLUME_COUNT_KEY] = volume_count
        return data

    def unparse_series(self, data):
        """Unparse series."""
        series = data.get(SERIES_KEY, {})
        series_name = series.get(NAME_KEY)
        volume_count = series.get(VOLUME_COUNT_KEY)
        if series_name:
            data[self.SERIES_TAG] = series_name
        if volume_count:
            data[self.VOLUME_COUNT_TAG] = volume_count
        return data

    def parse_volume(self, data):
        """Parse volume."""
        volume_number = data.get(self.VOLUME_TAG)
        issue_count = data.get(self.ISSUE_COUNT_TAG)
        if volume_number is not None or issue_count:
            data[VOLUME_KEY] = {}
            if volume_number:
                data[VOLUME_KEY][VOLUME_NUMBER_KEY] = volume_number
            if issue_count:
                data[VOLUME_KEY][VOLUME_ISSUE_COUNT_KEY] = issue_count
        return data

    def unparse_volume(self, data):
        """Unparse Volume."""
        volume_dict = data.get(VOLUME_KEY, {})
        volume_number = volume_dict.get(VOLUME_NUMBER_KEY)
        if volume_number is not None:
            data[self.VOLUME_TAG] = volume_number
        if issue_count := volume_dict.get(VOLUME_ISSUE_COUNT_KEY):
            data[self.ISSUE_COUNT_TAG] = issue_count
        return data

    def parse_publisher(self, data):
        """Parse Publisher."""
        if publisher_name := data.get(self.PUBLISHER_TAG):
            data[PUBLISHER_KEY] = {NAME_KEY: publisher_name}
        return data

    def unparse_publisher(self, data):
        """Unparse Publisher."""
        if publisher_name := data.get(PUBLISHER_KEY, {}).get(NAME_KEY):
            data[self.PUBLISHER_TAG] = publisher_name
        return data

    def parse_imprint(self, data):
        """Parse Imprint."""
        if imprint_name := data.get(self.IMPRINT_TAG):
            data[IMPRINT_KEY] = {NAME_KEY: imprint_name}
        return data

    def unparse_imprint(self, data):
        """Unparse imprint."""
        if imprint_name := data.get(IMPRINT_KEY, {}).get(NAME_KEY):
            data[self.IMPRINT_TAG] = imprint_name
        return data
