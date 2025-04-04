"""CoMet Reprints Transforms."""

from comicfn2dict.parse import comicfn2dict
from comicfn2dict.unparse import dict2comicfn
from glom import SKIP, Coalesce, Invoke, T

from comicbox.schemas.comicbox import REPRINTS_KEY
from comicbox.transforms.spec import MetaSpec
from comicbox.transforms.xml_reprints import (
    FILENAME_TO_REPRINT_SPECS,
    REPRINT_TO_FILENAME_SPECS,
)


def _skip(value):
    return not value


def comet_reprints_transform_to_cb(is_version_of_tag):
    """Transform comet is_version_of to reprints."""
    return MetaSpec(
        key_map={REPRINTS_KEY: is_version_of_tag},
        spec=(
            [
                Coalesce(
                    (
                        comicfn2dict,
                        dict(FILENAME_TO_REPRINT_SPECS),
                    ),
                    skip=_skip,
                    default=SKIP,
                )
            ],
        ),
    )


def comet_reprints_transform_from_cb(is_version_of_tag):
    """Transform comet is_version_of to reprints."""
    return MetaSpec(
        key_map={is_version_of_tag: REPRINTS_KEY},
        spec=(
            [
                Coalesce(
                    (
                        dict(REPRINT_TO_FILENAME_SPECS),
                        Invoke(dict2comicfn).specs(T).constants(ext=False),
                    ),
                    skip=_skip,
                    default=SKIP,
                ),
            ],
            set,
        ),
    )
