"""Title to Stories Transform Mixin."""

from comicbox.schemas.comicbox_mixin import PRICE_KEY, PRICES_KEY


class PriceMixin:
    """Title to Stories Transform Mixin."""

    PRICE_TAG = "price"

    def parse_price(self, data):
        """Parse price into prices."""
        price = data.get(self.PRICE_TAG)
        if price is not None:
            data[PRICES_KEY] = [{PRICE_KEY: price}]
        return data

    def unparse_price(self, data):
        """Unparse prices into single price."""
        if prices := data.get(PRICES_KEY):
            for price_obj in prices:
                price = price_obj.get(PRICE_KEY)
                if price is not None:
                    data[self.PRICE_TAG] = price
                    break
        return data
