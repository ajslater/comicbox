"""Transform string lists to comicbox name objects and back."""

from glom import SKIP, Coalesce, Iter, T, Val
from glom.grouping import Group

from comicbox.transforms.spec import MetaSpec


def _skip(val) -> bool:
    return not val


def name_obj_to_cb(key_map):
    """Create a name obj to string list key transform spec for a key map."""
    return MetaSpec(
        key_map=key_map,
        spec=(
            Coalesce(T, skip=_skip),
            Group({Coalesce(T, skip=_skip, default=SKIP): Val({})}),
        ),
    )


def name_obj_from_cb(key_map):
    """Create a name obj to string list key transform spec for a key map."""
    return MetaSpec(
        key_map=key_map,
        spec=(
            Coalesce(T, skip=_skip),
            Iter().filter().all(),
        ),
    )
