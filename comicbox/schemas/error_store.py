"""For marshmallow schemas that never fail on load, but instead just remove keys."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger
from marshmallow import Schema
from marshmallow.error_store import ErrorStore, merge_errors
from typing_extensions import override


class ClearingErrorStore(ErrorStore):
    """Take over error processing."""

    def _clean_error_list(
        self,
        key: str,
        error_list: list[str],
        cleaned_errors: dict[Any, Any],
    ) -> None:
        if cleaned_error_list := frozenset(error_list) - self._ignore_errors:
            cleaned_errors[key] = sorted(cleaned_error_list)

    def _clear_errors(self) -> None:
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

    def __init__(
        self,
        error_store: ErrorStore,
        data: Mapping[str, Any],
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

    def set_path(self, path: Path | str | None) -> None:
        """Set the path for error messages."""
        self._path = str(path) if path else None

    def __init__(
        self,
        path: Path | str | None = None,
        ignore_errors: list | tuple | frozenset | set | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize path and always use partial."""
        self._path = path = str(path) if path else path
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
        super()._invoke_schema_validators(error_store=error_store, **kwargs)

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
