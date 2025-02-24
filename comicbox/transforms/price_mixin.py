"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import PRICES_KEY


class PriceTransformMixin:
    """Price transformer."""

    PRICE_TAG = "price"

    def parse_price(self, data):
        """Parse price into prices."""
        price = data.get(self.PRICE_TAG)
        if price is not None:
            data[PRICES_KEY] = {"": price}
        return data

    def unparse_price(self, data):
        """Choose the first price."""
        if comicbox_prices := data.get(PRICES_KEY):
            for price in comicbox_prices.values():
                if price is not None:
                    data[self.PRICE_TAG] = price
                    break
        return data
