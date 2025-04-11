"""Skip keys instead of throwing errors."""

from abc import ABC
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path

from marshmallow import EXCLUDE, Schema
from marshmallow.decorators import (
    post_dump,
    post_load,
    pre_dump,
    pre_load,
)

from comicbox.empty import is_empty
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.error_store import ClearingErrorStoreSchema

LOG = getLogger(__name__)


class BaseSubSchema(ClearingErrorStoreSchema, ABC):
    """Base schema."""

    TAG_ORDER = ()

    @classmethod
    def pre_load_validate(cls, data):
        """Validate schema type first thing to fail as early as possible."""
        # Meant to be overridden in BaseSchema
        return data

    @trap_error(pre_load)
    def pre_load(self, data, **_kwargs):
        """Singular pre_load hook."""
        return self.pre_load_validate(data)

    @classmethod
    def clean_empties(cls, data: dict):
        """Clean empties from loaded data."""
        if isinstance(data, Mapping):
            data = {k: v for k, v in data.items() if not is_empty(v)}
        return data

    @trap_error(post_load)
    def post_load(self, data, **_kwargs):
        """Singular post_load hook."""
        return self.clean_empties(data)

    @pre_dump
    def pre_dump(self, data, **_kwargs):
        """Singular pre_dump hook."""
        return data

    @classmethod
    def _sort_tag_by_order(cls, data: dict) -> dict:
        """Sort tag by schema class order tuple."""
        result = {}
        for tag in cls.TAG_ORDER:
            value = data.get(tag)
            if is_empty(value):
                continue
            result[tag] = value
        return result

    @classmethod
    def sort_dump(cls, data: dict):
        """Sort dump by key."""
        if cls.TAG_ORDER:
            data = cls._sort_tag_by_order(data)
        elif isinstance(data, Mapping):
            data = {k: v for k, v in sorted(data.items()) if not is_empty(v)}
        return data

    @post_dump
    def post_dump(self, data: dict, **_kwargs):
        """Singular post_dump hook."""
        return self.sort_dump(data)

    def loadf(self, path):
        """Read the string from the designated file."""
        with Path(path).open("r") as f:
            str_data = f.read()
        return self.loads(str_data)

    def dumpf(self, data, path, **kwargs):
        """Write the string in the designated file."""
        str_data = self.dumps(data, **kwargs) + "\n"
        with Path(path).open("w") as f:
            f.write(str_data)

    class Meta(Schema.Meta):
        """Schema options."""

        unknown = EXCLUDE


class BaseSchema(BaseSubSchema, ABC):
    """Top level base schema that traps errors and records path."""

    ROOT_TAG = ""
    ROOT_DATA_KEY = ""
    ROOT_KEYPATH = ""
    EMBED_KEYPATH = ""
    HAS_PAGE_COUNT = False
    HAS_PAGES = False

    @classmethod
    def pre_load_validate(cls, data):
        """Validate the root tag so we don't confuse it with other JSON."""
        if not data:
            reason = "No data."
            LOG.debug(reason)
            data = {}
        elif cls.ROOT_TAG not in data and cls.ROOT_DATA_KEY not in data:
            reason = f"Root tag '{cls.ROOT_TAG}' not found in {tuple(data.keys())}."
            LOG.debug(reason)
            # Do not throw an exception so the trapper doesn't trap it and the
            # loader tries another schema. Return empty dict.
            data = {}
        return data
