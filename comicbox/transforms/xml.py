"""XML Metadata parser superclass."""

from logging import getLogger

from marshmallow.fields import List, Mapping, Tuple

from comicbox.transforms.base import BaseTransform

LOG = getLogger(__name__)


class XmlTransform(BaseTransform):
    """XML Schema customizations."""

    _SEQUENCE_OK_FIELDS = (List, Mapping, Tuple)

    def first_if_sequence(self, data):
        """If a collection is submitted for a single value, take the first value.

        Mostly useful when xmltodict parses multiple values into lists.
        """
        if not data:
            return data
        data_changes = {}
        for tag, value in data.items():
            try:
                field = self._schema.fields.get(tag)
                if not field:
                    continue
                if not isinstance(field, self._SEQUENCE_OK_FIELDS):
                    new_value = value
                    if isinstance(new_value, set | frozenset):
                        new_value = list(value)
                    if isinstance(new_value, list | tuple):
                        new_value = new_value[0]
                        data_changes[tag] = new_value
            except Exception:
                LOG.exception(f"{self._path} Getting first of sequence for tag {tag}")
                data_changes[tag] = None
        if data_changes:
            data.update(data_changes)
        return data

    @staticmethod
    def hoist_tag(tag, data, single_tag=None):
        """Hoist a double tag."""
        plural_tag = data.pop(tag, {})
        if not single_tag:
            single_tag = tag[:-1]
        return plural_tag.get(single_tag)

    @staticmethod
    def lower_tag(key, tag, data, value, single_tag=None):
        """Lower into a double tag."""
        if not value:
            return
        if not single_tag:
            single_tag = tag[:-1]
        data[key] = {single_tag: value}

    TO_COMICBOX_PRE_TRANSFORM = (
        *BaseTransform.TO_COMICBOX_PRE_TRANSFORM,
        first_if_sequence,
    )
