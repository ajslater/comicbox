"""Read and write reading lists in any registered format."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comicbox.exceptions import ReadingListFormatError
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.readinglists.registry import (
    ReadingListFormats,
    as_text,
    detect_format,
    get_format,
)
from comicbox.readinglists.schema import READING_LIST_KEY, ReadingListYamlSchema


@dataclass(frozen=True, slots=True)
class ReadingListResult:
    """
    A reading list read from a document.

    ``reading_list`` is the model's inner mapping. ``warnings`` say what the
    read had to drop or guess; they are returned, not logged.
    """

    reading_list: dict[str, Any]
    fmt: ReadingListFormats
    warnings: tuple[str, ...] = ()


def unwrap(reading_list: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept a list wrapped in its root tag, as a serialized document is."""
    if set(reading_list) == {READING_LIST_KEY}:
        inner = reading_list[READING_LIST_KEY]
        if isinstance(inner, Mapping):
            return inner
    return reading_list


def load_model(
    reading_list: Mapping[str, Any], path: Path | None = None
) -> dict[str, Any]:
    """Validate a list against the model, dropping what does not fit."""
    schema = get_schema(ReadingListYamlSchema, path=path)
    loaded: dict[str, Any] = schema.load({READING_LIST_KEY: dict(unwrap(reading_list))})  # pyright: ignore[reportAssignmentType]
    return loaded.get(READING_LIST_KEY) or {}


def _loads(
    text: str, fmt: ReadingListFormats | str | None, path: Path | None
) -> ReadingListResult:
    resolved = get_format(fmt) if fmt else detect_format(text)
    if resolved is None:
        reason = "Not a reading list in any format comicbox reads."
        if path:
            reason = f"{path}: {reason}"
        raise ReadingListFormatError(reason)
    transform = resolved.value.transform_class(path)
    document = transform.parse(text)
    reading_list = load_model(transform.to_reading_list(document), path)
    if not reading_list:
        reason = "The document holds no reading list."
        raise ReadingListFormatError(reason)
    return ReadingListResult(reading_list, resolved, tuple(transform.warnings))


def loads(
    data: str | bytes | bytearray, *, fmt: ReadingListFormats | str | None = None
) -> ReadingListResult:
    """Read a reading list from a string, detecting its format if not given."""
    return _loads(as_text(data), fmt, None)


def load(
    path: Path | str, *, fmt: ReadingListFormats | str | None = None
) -> ReadingListResult:
    """Read a reading list from a file, detecting its format if not given."""
    path = Path(path)
    return _loads(as_text(path.read_bytes()), fmt, path)


def _model_for_write(reading_list: Mapping[str, Any]) -> dict[str, Any]:
    model = load_model(reading_list)
    if not model:
        reason = "Nothing to write: the reading list is empty."
        raise ReadingListFormatError(reason)
    return model


def dumps(reading_list: Mapping[str, Any], fmt: ReadingListFormats | str) -> str:
    """
    Write a reading list in a format.

    The list is validated against the model first, so a hand-built mapping
    is checked before it is written. ``lost_fields`` says what the format
    cannot carry.
    """
    transform = get_format(fmt).value.transform_class()
    document = transform.from_reading_list(_model_for_write(reading_list))
    return transform.render(document)


def lost_fields(
    reading_list: Mapping[str, Any], fmt: ReadingListFormats | str
) -> tuple[str, ...]:
    """List the model keypaths this list uses that the format cannot carry."""
    transform = get_format(fmt).value.transform_class()
    return transform.losses(_model_for_write(reading_list))
