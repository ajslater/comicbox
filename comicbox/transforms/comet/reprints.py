"""CoMet Reprints Transforms."""

from comicbox.schemas.comicbox_mixin import REPRINTS_KEY
from comicbox.transforms.transform_map import KeyTransforms
from comicbox.transforms.xml_reprints import filename_to_reprint, reprint_to_filename


def _reprints_to_cb(_source_data, is_version_of):
    if isinstance(is_version_of, str):
        names = is_version_of.split(",;")
    else:
        names = is_version_of
    return [reprint for name in names if (reprint := filename_to_reprint(name))]


def _reprints_from_cb(_source_data, reprints):
    return {name for reprint in reprints if (name := reprint_to_filename(reprint))}


def comet_reprints_transform(is_version_of_tag):
    """Transform comet is_version_of to reprints."""
    return KeyTransforms(
        key_map={is_version_of_tag: REPRINTS_KEY},
        to_cb=_reprints_to_cb,
        from_cb=_reprints_from_cb,
    )
