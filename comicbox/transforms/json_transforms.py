"""JSON Transformer."""

from types import MappingProxyType

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.transforms.base import BaseTransform


class JsonTransform(BaseTransform):
    """JSON Transformer."""

    TOP_TAG_MAP = MappingProxyType({})

    def unwrap(self, data, wrap_tags=None) -> dict:
        """Move the top tags into the sub data."""
        top_tags = {}
        for key, tag in self.TOP_TAG_MAP.items():
            value = data.get(tag)
            if value not in EMPTY_VALUES:
                top_tags[key] = value
        sub_data = super().unwrap(data, wrap_tags=wrap_tags)
        sub_data.update(top_tags)
        return sub_data

    def wrap(self, sub_data, wrap_tags=None, **_kwargs):
        """Add the last modified timestamp."""
        top_tags = {}
        for key, tag in self.TOP_TAG_MAP.items():
            value = sub_data.get(key)
            if value not in EMPTY_VALUES:
                top_tags[tag] = value
        data = super().wrap(sub_data, wrap_tags=wrap_tags)
        data.update(top_tags)
        return data
