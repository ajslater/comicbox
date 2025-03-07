"""CoMet Reprints Transforms Mixin."""

from comicfn2dict.parse import comicfn2dict

from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    NAME_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
    VOLUME_ISSUE_COUNT_KEY,
    VOLUME_KEY,
    VOLUME_NUMBER_KEY,
)
from comicbox.transforms.xml_reprints import reprint_to_filename


class CoMetReprintsTransformMixin:
    """CoMet Reprints Mixin."""

    IS_VERSION_OF_TAG = "isVersionOf"

    @staticmethod
    def _parse_reprint_name(name, reprints):
        reprint = {}
        md = comicfn2dict(name)
        if series := md.get(SERIES_KEY):
            reprint[SERIES_KEY] = {NAME_KEY: series}
        if volume := md.get(VOLUME_KEY):
            reprint[VOLUME_KEY] = {VOLUME_NUMBER_KEY: volume}
        if issue := md.get(ISSUE_KEY):
            reprint[ISSUE_KEY] = issue
        if issue_count := md.get(VOLUME_ISSUE_COUNT_KEY):
            if VOLUME_KEY not in reprint:
                reprint[VOLUME_KEY] = {}
            reprint[VOLUME_KEY][VOLUME_ISSUE_COUNT_KEY] = issue_count
        if reprint:
            reprints.append(reprint)

    def parse_reprints(self, data):
        """Parse reprints from isVersionOf tag."""
        is_version_of = data.pop(self.IS_VERSION_OF_TAG, None)
        if not is_version_of:
            return data
        reprints = []
        if isinstance(is_version_of, str):
            names = is_version_of.split(",;")
        else:
            names = is_version_of
        for name in names:
            self._parse_reprint_name(name, reprints)
        if reprints:
            old_reprints = data.get(REPRINTS_KEY, [])
            reprints = old_reprints + reprints
            data[REPRINTS_KEY] = reprints
        return data

    def unparse_reprints(self, data):
        """Unparse reprints into comma delimited names."""
        reprints = data.pop(REPRINTS_KEY, None)
        if not reprints:
            return data
        names = set()
        for reprint in reprints:
            name = reprint_to_filename(reprint)
            if name:
                names.add(name)
        if names:
            data[self.IS_VERSION_OF_TAG] = names
        return data
