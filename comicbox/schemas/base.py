"""Skip keys instead of throwing errors."""
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path
from types import MappingProxyType

from marshmallow import EXCLUDE, Schema, ValidationError, post_dump, post_load
from marshmallow.error_store import ErrorStore, merge_errors
from simplejson.errors import JSONDecodeError

from comicbox.fields.fields import EMPTY_VALUES
from comicbox.schemas.decorators import trap_error

LOG = getLogger(__name__)


def sort_dict(d):
    """Recursively sort a Mapping type."""
    result = {}
    for k, v in sorted(d.items()):
        if isinstance(v, Mapping):
            result[k] = sort_dict(v)
        else:
            result[k] = v
    return result


class ClearingErrorStore(ErrorStore):
    """Take over error processing."""

    _IGNORE_ERRORS = frozenset("Field may not be null.")

    @classmethod
    def _clean_error_list(cls, key, error_list, cleaned_errors):
        cleaned_error_list = frozenset(error_list) - cls._IGNORE_ERRORS
        if cleaned_errors:
            cleaned_errors[key] = sorted(cleaned_error_list)

    def _clear_errors(self):
        if not self.errors:
            return
        cleaned_errors = {}
        if isinstance(self.errors, Mapping):
            for key, error_list in self.errors.items():
                self._clean_error_list(key, error_list, cleaned_errors)
        else:
            self._clean_error_list("UNKNOWN", self.errors, cleaned_errors)
        if cleaned_errors:
            LOG.warning(f"{self._path}: {cleaned_errors}")
        self.clear_errors = merge_errors(self.clear_errors, cleaned_errors)
        self.errors = {}

    def __init__(self, error_store: ErrorStore, data, path=None):
        """Take over error processing."""
        super().__init__()
        self._path = path
        self.clear_errors = {}
        self.errors = error_store.errors
        error_store.errors = {}
        self._data = data
        self._clear_errors()

    def store_error(self, *args, **kwargs):
        """Store error, but process and clear it."""
        super().store_error(*args, **kwargs)
        self._clear_errors()


class BaseSchema(Schema):
    """Common schema methods."""

    DATA_KEY_MAP = MappingProxyType({})

    @staticmethod
    def map_data_keys(key_map, schema):
        """Map data keys to a schema instance."""
        for native_key, comicbox_key in key_map.items():
            if native_key != comicbox_key and (
                field := schema.fields.get(comicbox_key)
            ):
                field.data_key = native_key

    def __init__(self, path=None, **kwargs):
        """Assign data_key mappings."""
        self._path = path
        super().__init__(partial=True, **kwargs)
        self.map_data_keys(self.DATA_KEY_MAP, self)

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

    def prune(self, data):
        """Prune data to only the used fields for the schema."""
        valid_keys = frozenset(self.fields.keys())
        pruned_data = {}
        for key, value in data.items():
            if key in valid_keys:
                pruned_data[key] = value
        return pruned_data

    def handle_error(self, exc, _data, **_kwargs):
        """Log errors as warnings."""
        if isinstance(exc, ValidationError):
            LOG.warning(f"Validation error occurred: {self._path} - {exc.messages}")
        else:
            LOG.warning(f"Unknown field error occurred: {self._path} - {exc}")

    @trap_error(post_load)
    def remove_empty_fields(self, data, **_kwargs):
        """Remove fields with empty values."""
        cleaned_data = {}
        for key, value in data.items():
            if value in EMPTY_VALUES:
                continue
            cleaned_data[key] = value
        return cleaned_data

    @post_dump
    def trim_keys(self, data, **_kwargs):
        """Trim extra keys."""
        del_keys = set()
        for key, value in data.items():
            if (
                self.DATA_KEY_MAP and key not in self.DATA_KEY_MAP
            ) or value in EMPTY_VALUES:
                del_keys.add(key)
        for key in del_keys:
            del data[key]
        return data

    def dump(self, *args, **kwargs):
        """Dump and recursively sort the results."""
        result = super().dump(*args, **kwargs)
        return sort_dict(result)

    def loads(self, *args, **kwargs):
        """Load string and also return the parsed metadata before load."""
        try:
            data = self.opts.render_module.loads(*args, **kwargs)
        except JSONDecodeError as exc:
            if exc.msg == "Expecting value" and exc.lineno == 1 and exc.colno == 1:
                LOG.warning(
                    f"Parsing {self._path} with {self.__class__.__name__}: Not JSON"
                )
                return None, None
            raise
        except Exception as exc:
            LOG.warning(f"Parsing {self._path} with {self.__class__.__name__}: {exc}")
            return None, None
        deserialized = self.load(data, **kwargs)
        return data, deserialized

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

    class Meta:
        """Schema options."""

        EXTRA_KEYS = ()
        unknown = EXCLUDE

        @classmethod
        def create_fields(cls, key_map, extra_keys=None, inherit_extra_keys=True):
            """Create fields from a key map and the the classes extra keys."""
            keys = tuple(key_map.values())
            if inherit_extra_keys:
                keys += cls.EXTRA_KEYS
            if extra_keys:
                keys += extra_keys

            return tuple(sorted(frozenset(keys)))
