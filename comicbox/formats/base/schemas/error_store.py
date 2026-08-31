"""For marshmallow schemas that never fail on load, but instead just remove keys."""

from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from loguru import logger
from marshmallow import Schema
from marshmallow.error_store import ErrorStore, merge_errors
from typing_extensions import override

# The archive path of the file currently being loaded/dumped, used to
# prefix warning messages. A ContextVar rather than schema instance state:
# schema instances are cached process-wide (see schemas/cache.py) and
# shared across the -j N worker threads, so an instance attribute would
# race — one thread's set_path would relabel another thread's in-flight
# warnings. Each thread (and each task in an event loop) sees its own
# value.
_current_path: ContextVar[str | None] = ContextVar("comicbox_schema_path", default=None)

_UNKNOWN_KEY = "UNKNOWN"
# Offending values go in the warning so the field name is actionable, but a
# whole embedded page list would drown the log.
_MAX_VALUE_REPR = 128


def _repr_value(value: Any) -> str:
    """Represent an offending value, truncated."""
    value_repr = repr(value)
    if len(value_repr) > _MAX_VALUE_REPR:
        value_repr = value_repr[:_MAX_VALUE_REPR] + "…"
    return value_repr


class ClearingErrorStore(ErrorStore):
    """Take over error processing."""

    def _clean_error_list(
        self,
        key: Any,
        error_list: Any,
        cleaned_errors: dict[Any, Any],
    ) -> None:
        """Filter ignored messages out of one field's errors."""
        if isinstance(error_list, Mapping):
            # Nested schema and collection errors arrive keyed by sub field
            # name or by index. Recurse so the leaf messages stay readable
            # instead of collapsing to a set of their container's keys.
            nested: dict[Any, Any] = {}
            for sub_key, sub_error_list in error_list.items():
                self._clean_error_list(sub_key, sub_error_list, nested)
            if nested:
                cleaned_errors[key] = nested
            return
        messages = error_list if isinstance(error_list, list | tuple) else [error_list]
        # str() keeps the set hashable and sortable whatever marshmallow put
        # in the list; ignored messages are plain strings and still match.
        if cleaned_error_list := frozenset(str(m) for m in messages) - (
            self._ignore_errors
        ):
            cleaned_errors[key] = sorted(cleaned_error_list)

    def _log_cleaned_errors(self, cleaned_errors: dict[Any, Any]) -> None:
        """
        Warn about the fields being dropped.

        Clearing the error store is what lets one bad tag not condemn a whole
        file, but dropping it silently makes malformed metadata indis-
        tinguishable from absent metadata. Name every field, and what was in
        it, so a silent drop is at least a visible one.
        """
        if not cleaned_errors:
            return
        data = self._data if isinstance(self._data, Mapping) else {}
        reports = []
        for key in sorted(cleaned_errors, key=str):
            messages = cleaned_errors[key]
            if key in data:
                reports.append(f"{key}={_repr_value(data[key])} {messages}")
            else:
                reports.append(f"{key} {messages}")
        path = f"{self._path}: " if self._path else ""
        logger.warning(f"{path}Dropped invalid metadata: {', '.join(reports)}")

    def _clear_errors(self) -> None:
        if not self.errors:
            return
        cleaned_errors = {}
        if isinstance(self.errors, Mapping):
            for key, error_list in self.errors.items():
                self._clean_error_list(key, error_list, cleaned_errors)
        else:
            self._clean_error_list(_UNKNOWN_KEY, self.errors, cleaned_errors)
        self._log_cleaned_errors(cleaned_errors)
        self.clear_errors = merge_errors(self.clear_errors, cleaned_errors)
        self.errors = {}

    def __init__(
        self,
        error_store: ErrorStore,
        data: Any,
        path: str | None = None,
        ignore_errors: frozenset | None = None,
    ) -> None:
        """Take over error processing."""
        super().__init__()
        self._path = path
        self.clear_errors = {}
        self.errors = error_store.errors
        error_store.errors = {}
        self._data = data
        self._ignore_errors = ignore_errors or frozenset()
        self._clear_errors()

    @override
    def store_error(self, *args: Any, **kwargs: Any) -> None:
        """Store error, but process and clear it."""
        super().store_error(*args, **kwargs)
        self._clear_errors()


class ClearingErrorStoreSchema(Schema):
    """Suppress Marshmallow errors to skip errored fields."""

    SUPPRESS_ERRORS: bool = True
    _IGNORE_ERRORS: frozenset[str] = frozenset({"Field may not be null."})

    @property
    def _path(self) -> str | None:
        """Current thread's file-path log prefix (see _current_path)."""
        return _current_path.get()

    def set_path(self, path: Path | str | None) -> None:
        """Set this thread's path prefix for error messages."""
        _current_path.set(str(path) if path else None)

    def __init__(
        self,
        path: Path | str | None = None,
        ignore_errors: list | tuple | frozenset | set | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize path and always use partial."""
        if path is not None:
            # Only set when explicitly supplied: marshmallow lazily
            # constructs Nested sub-schemas with no path mid-load, and
            # that must not clear the in-flight file's prefix.
            self.set_path(path)
        kwargs["partial"] = True
        ignore_errors = (
            frozenset() if ignore_errors is None else frozenset(ignore_errors)
        )
        self._ignore_errors = frozenset(ignore_errors) | self._IGNORE_ERRORS
        super().__init__(**kwargs)

    @override
    def _deserialize(
        self,
        data: Any,
        *,
        error_store: ErrorStore,
        **kwargs: Any,
    ) -> list | dict:
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPPRESS_ERRORS:
            error_store = ClearingErrorStore(
                error_store, data, self._path, ignore_errors=self._ignore_errors
            )
        return super()._deserialize(data, error_store=error_store, **kwargs)

    @override
    def _invoke_field_validators(
        self,
        *,
        error_store: ErrorStore,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPPRESS_ERRORS:
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
    ) -> None:
        """Skip keys and log warnings instead of throwing validation or type errors."""
        if self.SUPPRESS_ERRORS:
            error_store = ClearingErrorStore(
                error_store, data, self._path, ignore_errors=self._ignore_errors
            )
        super()._invoke_schema_validators(error_store=error_store, data=data, **kwargs)

    def _filter_list(self, error_list: list) -> list:
        return sorted(frozenset(error_list) - self._ignore_errors)

    def _filter_mapping(self, error: Mapping) -> dict:
        return {
            key: filtered
            for key, error_list in error.items()
            if (filtered := self._filter_list(error_list))
        }

    def _log_warnings(
        self,
        error_class: type | None,
        errors: Mapping | list,
    ) -> None:
        if not errors:
            return
        path = f"{self._path}: " if self._path else ""
        error_name = f"{error_class.__name__} - " if error_class else ""
        message = f"{path}{error_name}{errors}"
        logger.warning(message)

    @override
    def handle_error(
        self,
        error: Any,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        """Log unignored errors at WARNING; ignored errors are dropped."""
        if hasattr(error, "normalized_messages"):
            error_class = type(error)
            error = error.normalized_messages()
        elif hasattr(error, "message"):
            error_class = type(error)
            error = error.message
        else:
            error_class = None

        if isinstance(error, Mapping):
            warning_errors = self._filter_mapping(error)
        else:
            error_list = error if isinstance(error, list) else [error]
            warning_errors = self._filter_list(error_list)

        self._log_warnings(error_class, warning_errors)
