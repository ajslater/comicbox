"""For marshmallow schemas that never fail on load, but instead just remove keys."""

from collections.abc import Mapping
from logging import getLogger

from marshmallow import Schema, ValidationError
from marshmallow.error_store import ErrorStore, merge_errors

LOG = getLogger(__name__)


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


class ClearingErrorStoreSchema(Schema):
    """Suppress Marshmallow errors to skip errored fields."""

    SUPRESS_ERRORS = True

    def __init__(self, **kwargs):
        """Initialize path and always use partial."""
        kwargs["partial"] = True
        self._path = kwargs.pop("path", None)
        super().__init__(**kwargs)

    def _deserialize(self, data, *, error_store: ErrorStore, **kwargs):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(error_store, data, self._path)
        return super()._deserialize(data, error_store=error_store, **kwargs)

    def _invoke_field_validators(self, *, error_store: ErrorStore, data, **kwargs):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(error_store, data, self._path)
        super()._invoke_field_validators(error_store=error_store, data=data, **kwargs)

    def _invoke_schema_validators(
        self,
        *,
        error_store: ErrorStore,
        data,
        **kwargs,
    ):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(error_store, data, self._path)
        super()._invoke_schema_validators(error_store=error_store, **kwargs)

    def handle_error(self, error, *_args, **_kwargs):
        """Log errors as warnings."""
        if isinstance(error, ValidationError):
            LOG.warning(f"Validation error occurred: {self._path} - {error.messages}")
        else:
            LOG.warning(f"Unknown field error occurred: {self._path} - {error}")
