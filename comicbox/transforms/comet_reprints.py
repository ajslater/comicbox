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
from comicbox.transforms.transform_map import (
    KeyTransforms,
    create_transform_map,
    transform_map,
)
from comicbox.transforms.xml_reprints import reprint_to_filename


class CoMetReprintsTransformMixin:
    """CoMet Reprints Mixin."""

    IS_VERSION_OF_TAG = "isVersionOf"
    COMET_REPRINTS_TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                SERIES_KEY: f"{SERIES_KEY}.{NAME_KEY}",
                VOLUME_KEY: f"{VOLUME_KEY}.{VOLUME_NUMBER_KEY}",
                ISSUE_KEY: ISSUE_KEY,
                VOLUME_ISSUE_COUNT_KEY: f"{VOLUME_KEY}.{VOLUME_ISSUE_COUNT_KEY}",
            }
        )
    )

    @classmethod
    def _parse_reprint_name(cls, name, reprints):
        md = comicfn2dict(name)
        reprint = transform_map(cls.COMET_REPRINTS_TRANSFORM_MAP, md)
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
