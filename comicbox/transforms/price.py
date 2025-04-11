"""Title to Stories Transform Mixin."""

from glom import Coalesce, Fill, Iter, T

from comicbox.schemas.comicbox import PRICES_KEY
from comicbox.transforms.spec import MetaSpec


def price_transform_to_cb(price_tag: str):
    """Create a price transform from native to comicbox."""
    return MetaSpec(key_map={PRICES_KEY: price_tag}, spec=(Fill({"": T}),))


def price_transform_from_cb(price_tag: str):
    """Create a price transform from comicbox to native."""
    return MetaSpec(
        key_map={price_tag: PRICES_KEY},
        spec=(Coalesce(T.values()), Iter().first()),
    )
