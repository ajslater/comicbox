"""For marshmallow schemas that never fail on load, but instead just remove keys."""

from collections.abc import Mapping

from loguru import logger
from marshmallow import Schema
from marshmallow.error_store import ErrorStore, merge_errors
from typing_extensions import override


class ClearingErrorStore(ErrorStore):
    """Take over error processing."""

    def _clean_error_list(self, key, error_list, cleaned_errors):
        if cleaned_error_list := frozenset(error_list) - self._ignore_errors:
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
        self.clear_errors = merge_errors(self.clear_errors, cleaned_errors)
        self.errors = {}

    def __init__(self, error_store: ErrorStore, data, path=None, ignore_errors=None):
        """Take over error processing."""
        super().__init__()
        self._path = path
        self.clear_errors = {}
        self.errors = error_store.errors
        error_store.errors = {}
        self._data = data
        self._ignore_errors = ignore_errors if ignore_errors else frozenset()
        self._clear_errors()

    @override
    def store_error(self, *args, **kwargs):
        """Store error, but process and clear it."""
        super().store_error(*args, **kwargs)
        self._clear_errors()


class ClearingErrorStoreSchema(Schema):
    """Suppress Marshmallow errors to skip errored fields."""

    SUPRESS_ERRORS: bool = True
    _IGNORE_ERRORS: frozenset[str] = frozenset({"Field may not be null."})

    def __init__(
        self, ignore_errors: list | tuple | frozenset | set | None = None, **kwargs
    ):
        """Initialize path and always use partial."""
        kwargs["partial"] = True
        self._path = kwargs.pop("path", None)
        ignore_errors = (
            frozenset() if ignore_errors is None else frozenset(ignore_errors)
        )
        self._ignore_errors = frozenset(ignore_errors) | self._IGNORE_ERRORS
        super().__init__(**kwargs)

    @override
    def _deserialize(self, data, *, error_store: ErrorStore, **kwargs):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(
                error_store, data, self._path, ignore_errors=self._ignore_errors
            )
        return super()._deserialize(data, error_store=error_store, **kwargs)

    @override
    def _invoke_field_validators(self, *, error_store: ErrorStore, data, **kwargs):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(
                error_store, data, self._path, ignore_errors=self._ignore_errors
            )
        super()._invoke_field_validators(error_store=error_store, data=data, **kwargs)

    @override
    def _invoke_schema_validators(
        self,
        *,
        error_store: ErrorStore,
        data,
        **kwargs,
    ):
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPRESS_ERRORS:
            error_store = ClearingErrorStore(
                error_store, data, self._path, ignore_errors=self._ignore_errors
            )
        super()._invoke_schema_validators(error_store=error_store, **kwargs)

    def _split_list_errors(self, error_list: list):
        error_set = frozenset(error_list)
        debug_error_set = error_set & self._ignore_errors
        debug_errors = sorted(debug_error_set)
        warning_errors = sorted(error_set - debug_error_set)
        return debug_errors, warning_errors

    def _split_mapping_errors(self, error: Mapping):
        debug_errors = {}
        warning_errors = {}
        for key, error_list in error.items():
            debug_error_list, warning_error_list = self._split_list_errors(error_list)
            if debug_error_list:
                debug_errors[key] = debug_error_list
            if warning_error_list:
                warning_errors[key] = warning_error_list
        return debug_errors, warning_errors

    def _log_errors(
        self, loglevel: str, error_class: type | None, errors: Mapping | list
    ):
        if not errors:
            return
        path = f"{self._path}: " if self._path else ""
        error_name = f"{error_class.__name__} - " if error_class else ""
        message = f"{path}{error_name}{errors}"
        logger.log(loglevel, message)

    @override
    def handle_error(self, error, *_args, **_kwargs):
        """Log errors by severity."""
        if hasattr(error, "normalized_messages"):
            error_class = type(error)
            error = error.normalized_messages()
        elif hasattr(error, "message"):
            error_class = type(error)
            error = error.message
        else:
            error_class = None

        if isinstance(error, Mapping):
            debug_errors, warning_errors = self._split_mapping_errors(error)
        else:
            error_list = error if isinstance(error, list) else [error]
            debug_errors, warning_errors = self._split_list_errors(error_list)

        logs = {"WARNING": warning_errors, "DEBUG": debug_errors}

        for loglevel, errors in logs.items():
            self._log_errors(loglevel, error_class, errors)
