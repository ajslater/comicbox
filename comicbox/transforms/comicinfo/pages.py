"""ComicInfo Pages Transformer creator."""

from collections.abc import Mapping

from glom import SKIP, Coalesce, Fill, Merge, T
from glom.grouping import Group

from comicbox.empty import is_empty
from comicbox.schemas.comicbox import PAGES_KEY
from comicbox.schemas.comicinfo import IMAGE_ATTRIBUTE
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

_KEY_SPEC = Coalesce(T[IMAGE_ATTRIBUTE], skip=is_empty, default=SKIP)


def comicinfo_pages_to_cb(pages_key_path: str, page_key_map: Mapping):
    """Transform comicinfo pages into comicbox."""
    page_spec = create_specs_to_comicbox(
        MetaSpec(key_map=page_key_map, inherit_root_keypath=False)
    )
    value_spec = Coalesce(dict(page_spec), skip=is_empty, default=SKIP)
    value_spec = Fill(value_spec)

    return MetaSpec(
        key_map={PAGES_KEY: pages_key_path},
        spec=(Group({_KEY_SPEC: value_spec}),),
    )


def comicinfo_pages_from_cb(pages_key_path: str, page_key_map: Mapping):
    """Transform comicbox pages into comicinfo."""
    page_spec = create_specs_from_comicbox(
        MetaSpec(key_map=page_key_map, inherit_root_keypath=False)
    )

    return MetaSpec(
        key_map={pages_key_path: PAGES_KEY},
        spec=(
            T.items(),
            [
                Coalesce(
                    (
                        {
                            "index": {IMAGE_ATTRIBUTE: T[0]},
                            "page": (T[1], dict(page_spec)),
                        },
                        T.values(),
                        Merge(),
                    ),
                    skip=is_empty,
                    default=SKIP,
                )
            ],
        ),
    )
