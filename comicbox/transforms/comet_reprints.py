"""CoMet Reprints Transforms Mixin."""

from comicfn2dict.parse import comicfn2dict

from comicbox.schemas.comicbox_mixin import (
    REPRINTS_KEY,
)
from comicbox.transforms.transform_map import (
    transform_map,
)
from comicbox.transforms.xml_reprints import (
    REPRINTS_TO_FILENAME_TRANSFORM_MAP,
    reprint_to_filename,
)


class CoMetReprintsTransformMixin:
    """CoMet Reprints Mixin."""

    IS_VERSION_OF_TAG = "isVersionOf"

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
            md = comicfn2dict(name)
            reprint = transform_map(REPRINTS_TO_FILENAME_TRANSFORM_MAP.inverse, md)
            if reprint:
                reprints.append(reprint)
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
