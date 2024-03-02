"""Nested Publishing Tags."""

from comicbox.schemas.comicbox_mixin import (
    ISSUE_COUNT_KEY,
    SERIES_KEY,
    SERIES_NAME_KEY,
    VOLUME_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)


class NestedPublishingTagsMixin:
    """Nested Publishing Tags."""

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
                data[SERIES_KEY][SERIES_NAME_KEY] = series_name
            if volume_count:
                data[SERIES_KEY][VOLUME_COUNT_KEY] = volume_count
        return data

    def unparse_series(self, data):
        """Unparse series."""
        series = data.get(SERIES_KEY, {})
        series_name = series.get(SERIES_NAME_KEY)
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
                data[VOLUME_KEY][ISSUE_COUNT_KEY] = issue_count
        return data

    def unparse_volume(self, data):
        """Unparse Volume."""
        volume_dict = data.get(VOLUME_KEY, {})
        volume_number = volume_dict.get(VOLUME_NUMBER_KEY)
        if volume_number is not None:
            data[self.VOLUME_TAG] = volume_number
        if issue_count := volume_dict.get(ISSUE_COUNT_KEY):
            data[self.ISSUE_COUNT_TAG] = issue_count
        return data
