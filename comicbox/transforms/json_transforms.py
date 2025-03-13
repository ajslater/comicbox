"""JSON Transformer."""

from bidict import frozenbidict

from comicbox.transforms.base import BaseTransform
from comicbox.transforms.transform_map import transform_map


class JsonTransform(BaseTransform):
    """JSON Transformer."""

    TOP_TAG_MAP = frozenbidict()
    # TODO could wrap be just a case of top tag map?

    def unwrap(self, data, wrap_tags="") -> dict:
        """Move the top tags into the sub data."""
        top_tags = transform_map(self.TOP_TAG_MAP, data)
        sub_data = super().unwrap(data, wrap_tags=wrap_tags)
        sub_data.update(top_tags)
        return sub_data

    def wrap(self, sub_data, wrap_tags="", **_kwargs):
        """Add the last modified timestamp."""
        top_tags = transform_map(self.TOP_TAG_MAP.inverse, sub_data)
        data = super().wrap(sub_data, wrap_tags=wrap_tags)
        data.update(top_tags)
        return data
