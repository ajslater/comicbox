"""Read and write reading lists in any registered format."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comicbox.empty import is_empty
from comicbox.exceptions import ReadingListFormatError
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.base.schemas.error_store import unlogged_drops
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    MONTH_KEY,
    STORE_DATE_KEY,
    YEAR_KEY,
)
from comicbox.readinglists.changes import describe_changes
from comicbox.readinglists.losses import describe_losses
from comicbox.readinglists.registry import (
    ReadingListFormats,
    as_text,
    detect_format,
    get_format,
)
from comicbox.readinglists.schema import (
    DATE_KEY,
    ENTRIES_KEY,
    READING_LIST_KEY,
    EntrySchema,
    ReadingListYamlSchema,
)
from comicbox.readinglists.syntax import syntax_error

# A year, or a year and month: a date that names no day.
_PARTIAL_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")


@dataclass(frozen=True, slots=True)
class ReadingListResult:
    """
    A reading list read from a document.

    ``reading_list`` is the model's inner mapping. ``warnings`` name every
    key or value the read dropped, changed or guessed, each starting with
    its path; they are returned, not logged.
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


def _partial_dates(
    entry: Mapping[str, Any], prefix: str, warnings: list[str]
) -> Mapping[str, Any]:
    """
    Read a cover date that names no day as its year and month.

    ``2006`` and ``2006-07`` are a year and a month, never a cover date: a
    reading list does not guess the day. A store date that names no day is
    dropped. Either is a warning.
    """
    entry_date = entry.get(DATE_KEY)
    if not isinstance(entry_date, Mapping):
        return entry
    result = dict(entry_date)
    for key in (COVER_DATE_KEY, STORE_DATE_KEY):
        value = result.get(key)
        if not isinstance(value, str) or not (
            match := _PARTIAL_DATE_RE.match(value.strip())
        ):
            continue
        del result[key]
        here = f"{prefix}.{DATE_KEY}.{key}: {value!r} is not a whole date"
        if key == STORE_DATE_KEY:
            warnings.append(f"{here}; dropped")
            continue
        year, month = match.groups()
        result.setdefault(YEAR_KEY, int(year))
        read = f"year {year}"
        if month:
            result.setdefault(MONTH_KEY, int(month))
            read += f", month {int(month)}"
        warnings.append(f"{here}; read as {read}")
    return {**entry, DATE_KEY: result}


def _load_entries(raw_entries: Any, warnings: list[str]) -> list[dict[str, Any]]:
    """Load entries one by one, naming what each loses and any not loaded."""
    if is_empty(raw_entries):
        return []
    if isinstance(raw_entries, Mapping):
        raw_entries = [raw_entries]
    if not isinstance(raw_entries, list | tuple):
        warnings.append(f"{ENTRIES_KEY}: {raw_entries!r} is not a list; dropped")
        return []
    schema = get_schema(EntrySchema)
    entries = []
    for position, raw_entry in enumerate(raw_entries, start=1):
        prefix = f"{ENTRIES_KEY} #{position}"
        if is_empty(raw_entry):
            continue
        if not isinstance(raw_entry, Mapping):
            warnings.append(f"{prefix}: {raw_entry!r} is not an entry; dropped")
            continue
        dated = _partial_dates(raw_entry, prefix, warnings)
        entry: dict[str, Any] = schema.load(dated)  # pyright: ignore[reportAssignmentType]
        warnings.extend(describe_changes(dated, entry, prefix))
        if entry:
            entries.append(entry)
    return entries


def load_model_with_warnings(
    reading_list: Mapping[str, Any], path: Path | None = None
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """
    Validate a list against the model, naming everything that does not fit.

    Each warning starts with the path of what was dropped or changed:
    ``start_year``, ``entries #3.series``. They are returned, not logged.
    """
    raw = dict(unwrap(reading_list))
    raw_entries = raw.pop(ENTRIES_KEY, None)
    schema = get_schema(ReadingListYamlSchema, path=path)
    with unlogged_drops():
        loaded: dict[str, Any] = schema.load({READING_LIST_KEY: raw})  # pyright: ignore[reportAssignmentType]
        header = dict(loaded.get(READING_LIST_KEY) or {})
        warnings = list(describe_changes(raw, header))
        if entries := _load_entries(raw_entries, warnings):
            header[ENTRIES_KEY] = entries
    return header, tuple(warnings)


def load_model(
    reading_list: Mapping[str, Any], path: Path | None = None
) -> dict[str, Any]:
    """Validate a list against the model, dropping what does not fit."""
    return load_model_with_warnings(reading_list, path)[0]


def _loads(
    text: str, fmt: ReadingListFormats | str | None, path: Path | None
) -> ReadingListResult:
    resolved = get_format(fmt) if fmt else detect_format(text)
    if resolved is None:
        reason = (
            syntax_error(text) or "Not a reading list in any format comicbox reads."
        )
        raise ReadingListFormatError(reason)
    transform = resolved.value.transform_class(path)
    document = transform.parse(text)
    reading_list, warnings = load_model_with_warnings(
        transform.to_reading_list(document), path
    )
    if not reading_list:
        reason = "The document holds no reading list."
        raise ReadingListFormatError(reason)
    return ReadingListResult(reading_list, resolved, (*transform.warnings, *warnings))


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
    """
    Name what writing this list in a format and reading it back would change.

    Exact: the list is written, read back and compared. Header keys such as
    ``sources``, entry paths such as ``entries.date.cover_date``, and
    ``entries #2, #5`` for entries the format cannot write at all.
    """
    resolved = get_format(fmt)
    model = _model_for_write(reading_list)
    transform = resolved.value.transform_class()
    text = transform.render(transform.from_reading_list(model))
    back = _loads(text, resolved, None).reading_list
    return describe_losses(model, back, transform.unwritable(model))
