"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import PRICES_KEY
from comicbox.transforms.transform_map import KeyTransforms


def price_to_obj(price):
    """Price to a language keyed price object."""
    # TODO get language from data
    return {"": price} if price is not None else None


def obj_to_price(comicbox_prices):
    """Return first price."""
    # TODO match price to language
    return next(iter(comicbox_prices.values())) if comicbox_prices else None


class PriceTransformMixin:
    """Price transformer."""

    PRICE_TAG = "price"
    PRICE_KEY_TRANSFORM = KeyTransforms(
        key_map={"price": PRICES_KEY}, to_cb=price_to_obj, from_cb=obj_to_price
    )
