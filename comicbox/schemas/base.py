"""Skip keys instead of throwing errors."""

from abc import ABC
from logging import getLogger
from pathlib import Path
from types import MappingProxyType

from marshmallow import EXCLUDE, Schema, ValidationError
from marshmallow.decorators import (
    post_dump,
    post_load,
    pre_dump,
    pre_load,
)
from marshmallow.error_store import ErrorStore

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.error_store import ClearingErrorStore

LOG = getLogger(__name__)


class BaseSubSchema(Schema, ABC):
    """Base schema."""

    TAG_ORDER = ()
    TAG_MOVE_MAP = MappingProxyType({})

    def __init__(self, **kwargs):
        """Initialize path and always use partial."""
        kwargs["partial"] = True
        self._path = kwargs.pop("path", None)
        super().__init__(**kwargs)

    @classmethod
    def pre_load_validate(cls, data):
        """Validate schema type first thing to fail as early as possible."""
        # Meant to be overridden in BaseSchema
        return data

    @classmethod
    def _rename_tag(cls, data, from_tag, to_tag):
        """Move one tag to another."""
        if root := data.pop(from_tag, None):
            data[to_tag] = root
        return data

    @trap_error(pre_load)
    def pre_load(self, data, **_kwargs):
        """Singular pre_load hook."""
        data = self.pre_load_validate(data)
        if data and (args := self.TAG_MOVE_MAP.get("pre_load")):
            data = dict(data)
            data = self._rename_tag(data, *args)
        return data

    @classmethod
    def _remove_empty_values(cls, data, phase=""):
        """Remove fields with empty values."""
        if not data:
            return data
        data = dict(data)
        for key, value in tuple(data.items()):
            if value in EMPTY_VALUES:
                del data[key]
            elif args := cls.TAG_MOVE_MAP.get(phase):
                cls._rename_tag(data, *args)

        return data

    @trap_error(post_load)
    def post_load(self, data, **_kwargs):
        """Singular post_load hook."""
        return self._remove_empty_values(data, "post_load")

    @pre_dump
    def pre_dump(self, data, **_kwargs):
        """Singular pre_dump hook."""
        return self._remove_empty_values(data, "pre_dump")

    @classmethod
    def _sort_tag_by_order(cls, data: dict, remove_empty: bool = True) -> dict:  # noqa: FBT002
        """Sort tag by schema class order tuple."""
        result = {}
        for tag in cls.TAG_ORDER:
            value = data.get(tag)
            if remove_empty and value in EMPTY_VALUES:
                continue
            result[tag] = value
        return result

    @classmethod
    def sort_dump(cls, data: dict, phase=""):
        """Sort dump by key."""
        if cls.TAG_ORDER:
            if args := cls.TAG_MOVE_MAP.get(phase):
                cls._rename_tag(data, *args)
            data = cls._sort_tag_by_order(data)
        elif isinstance(data, dict):
            data = cls._remove_empty_values(data, phase=phase)
            data = dict(sorted(data.items()))
        return data

    @post_dump
    def post_dump(self, data: dict, **_kwargs):
        """Singular post_dump hook."""
        return self.sort_dump(data, "post_dump")

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
    CONFIG_KEYS = frozenset()
    FILENAME = ""
    WRAP_TAGS = ()
    EMBED_KEY_PATH = ""
    HAS_PAGE_COUNT = False
    HAS_PAGES = False

    def set_path(self, path):
        """Set the path after the instance is created."""
        self._path = path

    def _invoke_field_validators(self, *, error_store: ErrorStore, data, **kwargs):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        clearing_error_store = ClearingErrorStore(error_store, data, self._path)
        super()._invoke_field_validators(
            error_store=clearing_error_store, data=data, **kwargs
        )

    def _invoke_schema_validators(
        self,
        *,
        error_store: ErrorStore,
        data,
        **kwargs,
    ):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        clearing_error_store = ClearingErrorStore(error_store, data, self._path)
        super()._invoke_schema_validators(error_store=clearing_error_store, **kwargs)

    def handle_error(self, error, *_args, **_kwargs):
        """Log errors as warnings."""
        if isinstance(error, ValidationError):
            LOG.warning(f"Validation error occurred: {self._path} - {error.messages}")
        else:
            LOG.warning(f"Unknown field error occurred: {self._path} - {error}")

    @classmethod
    def pre_load_validate(cls, data):
        """Validate the root tag so we don't confuse it with other JSON."""
        if not data:
            reason = "No data."
            LOG.debug(reason)
            data = {}
        elif cls.ROOT_TAG not in data:
            reason = f"Root tag '{cls.ROOT_TAG}' not found in {tuple(data.keys())}."
            LOG.debug(reason)
            # Do not throw an exception so the trapper doesn't trap it and the
            # loader tries another schema. Return empty dict.
            data = {}
        return data
