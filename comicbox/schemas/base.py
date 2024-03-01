"""Skip keys instead of throwing errors."""

from abc import ABC
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path

from marshmallow import EXCLUDE, Schema, ValidationError, post_dump, post_load
from marshmallow.decorators import pre_load
from marshmallow.error_store import ErrorStore

from comicbox.dict_funcs import sort_dict
from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.error_store import ClearingErrorStore

LOG = getLogger(__name__)


class BaseSubSchema(Schema, ABC):
    """Base schema."""

    def __init__(self, **kwargs):  # noqa ARG002
        kwargs["partial"] = True
        self._path = kwargs.pop("path", None)
        super().__init__(**kwargs)

    def _remove_null_values(self, data):
        """Remove fields with empty values."""
        for key, value in tuple(data.items()):
            if value in EMPTY_VALUES:
                del data[key]
        return data

    @trap_error(post_load)
    def remove_empty_keys_on_load(self, data, **_kwargs):
        """Remove null keys."""
        return self._remove_null_values(data)

    @post_dump
    def remove_empty_keys_on_dump(self, data, **_kwargs):
        """Remove null keys."""
        return self._remove_null_values(data)

    def dump(self, *args, **kwargs):
        """Dump and recursively sort the results."""
        result = super().dump(*args, **kwargs)
        if isinstance(result, Mapping):
            result = sort_dict(result)
        return result

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

    CONFIG_KEYS = frozenset()
    FILENAME = ""
    ROOT_TAGS = ("",)

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

    @trap_error(pre_load)
    def validate_root_tag(self, data, **_kwargs):
        """Validate the root tag so we don't confuse it with other JSON."""
        if data and self.ROOT_TAGS[0] not in data:
            return {}
        return data
