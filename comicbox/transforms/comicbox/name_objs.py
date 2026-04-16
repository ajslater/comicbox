"""Transform string lists to comicbox name objects and back."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import comicbox.identifiers.identifiers

from glom import SKIP, Coalesce, Iter, T, Val
from glom.grouping import Group

from comicbox.transforms.base import skip_not
from comicbox.transforms.spec import MetaSpec


def name_obj_to_cb(
    key_map: "comicbox.identifiers.identifiers.frozenbidict",
) -> MetaSpec:
    """Create a name obj to string list key transform spec for a key map."""
    return MetaSpec(
        key_map=key_map,
        spec=(
            Coalesce(T, skip=skip_not),
            Group({Coalesce(T, skip=skip_not, default=SKIP): Val({})}),
        ),
    )


def name_obj_from_cb(
    key_map: "comicbox.identifiers.identifiers.frozenbidict",
) -> MetaSpec:
    """Create a name obj to string list key transform spec for a key map."""
    return MetaSpec(
        key_map=key_map,
        spec=(
            Coalesce(T, skip=skip_not),
            Iter().filter().all(),
        ),
    )
