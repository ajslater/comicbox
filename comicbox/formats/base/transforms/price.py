"""Title to Stories Transform Mixin."""

from glom import Coalesce, Fill, Iter, T

from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import PRICES_KEY


def price_transform_to_cb(price_tag: str) -> MetaSpec:
    """Create a price transform from native to comicbox."""
    return MetaSpec(key_map={PRICES_KEY: price_tag}, spec=(Fill({"": T}),))


def price_transform_from_cb(price_tag: str) -> MetaSpec:
    """Create a price transform from comicbox to native."""
    return MetaSpec(
        key_map={price_tag: PRICES_KEY},
        spec=(Coalesce(T.values()), Iter().first()),
    )
