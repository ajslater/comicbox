"""A frozen Confuse AttrDict."""

from confuse.templates import AttrDict
from typing_extensions import override


class FrozenAttrDict(AttrDict):
    """A frozen AttrDict."""

    @override
    def __setattr__(self, key, value):
        """Not Allowed."""
        raise NotImplementedError

    def __set__(self, key, value):
        """Not Allowed."""
        raise NotImplementedError

    def __delete__(self, key):
        """Not Allowed."""
        raise NotImplementedError
