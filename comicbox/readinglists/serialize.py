"""Read and write reading lists in any registered format."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comicbox.empty import is_empty
from comicbox.exceptions import ReadingListFormatError
from comicbox.formats.base.fields.time_fields import DateParts, date_parts
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.base.schemas.error_store import unlogged_drops
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    MONTH_KEY,
    STORE_DATE_KEY,
    YEAR_KEY,
)
from comicbox.readinglists.changes import describe_changes, quote_value
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
    TAGS_KEY,
    EntrySchema,
    ReadingListYamlSchema,
)
from comicbox.readinglists.syntax import refuse_yaml_aliases, syntax_error
from comicbox.readinglists.text import clean_tree

# A year, or a year and month: a date that names no day.
_YAML_LEXER = "yaml"


@contextmanager
def readable_depth() -> Generator[None]:
    """Turn nesting too deep for the parsers into a format error."""
    try:
        yield
    except RecursionError:
        reason = "The document is nested too deeply to read."
        # From None: the recursion's own traceback is thousands of frames.
        raise ReadingListFormatError(reason) from None


@dataclass(frozen=True, slots=True)
class ReadingListResult:
    """
    A reading list read from a document or fetched from a database.

    ``reading_list`` is the model's inner mapping. ``fmt`` is the format the
    document was in, or None for a list built from an online database's
    records, such as a Metron reading list. ``warnings`` name every key or
    value the read dropped, changed or guessed, each starting with its
    path; they are returned, not logged.
    """

    reading_list: dict[str, Any]
    fmt: ReadingListFormats | None
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
    Read a cover date that names a year but no day as its year and month.

    ``2006``, ``2006-07`` and ``July 2006`` are a year and a month, never a
    cover date, as in a comic: a reading list does not guess the day. A store
    date that names no day is dropped. Either is a warning.
    """
    entry_date = entry.get(DATE_KEY)
    if not isinstance(entry_date, Mapping):
        return entry
    result = dict(entry_date)
    for key in (COVER_DATE_KEY, STORE_DATE_KEY):
        value = result.get(key)
        if (parts := _partial_date(value)) is None:
            continue
        del result[key]
        here = f"{prefix}.{DATE_KEY}.{key}: {quote_value(value)} is not a whole date"
        if key == STORE_DATE_KEY:
            warnings.append(f"{here}; dropped")
            continue
        warnings.append(f"{here}; {_read_partial(result, parts)}")
    return {**entry, DATE_KEY: result}


def _read_partial(result: dict[str, Any], parts: DateParts) -> str:
    """
    Fill a date's year and month from a partial cover date, and say how.

    Only where the entry's own date agrees: a year or month it already gives
    otherwise keeps the partial date out whole, so no date from neither
    source is made.
    """
    for key, value in ((YEAR_KEY, parts.year), (MONTH_KEY, parts.month)):
        given = result.get(key)
        if value is not None and given is not None and given != value:
            return f"dropped, as the entry gives {key} {given}"
    result[YEAR_KEY] = parts.year
    read = f"year {parts.year}"
    if parts.month is not None:
        result[MONTH_KEY] = parts.month
        read += f", month {parts.month}"
    return f"read as {read}"


def _partial_date(value: Any) -> DateParts | None:
    """
    Get the parts of a date that names a year but no day; None for any other.

    An unquoted YAML ``2006`` is a number, and is read as a year too.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or (parts := date_parts(value.strip())) is None:
        return None
    return parts if parts.year is not None and not parts.whole else None


def _load_entries(raw_entries: Any, warnings: list[str]) -> list[dict[str, Any]]:
    """Load entries one by one, naming what each loses and any not loaded."""
    if is_empty(raw_entries):
        return []
    if isinstance(raw_entries, Mapping):
        raw_entries = [raw_entries]
    if not isinstance(raw_entries, list | tuple):
        warnings.append(
            f"{ENTRIES_KEY}: {quote_value(raw_entries)} is not a list; dropped"
        )
        return []
    schema = get_schema(EntrySchema)
    entries = []
    for position, raw_entry in enumerate(raw_entries, start=1):
        prefix = f"{ENTRIES_KEY} #{position}"
        if is_empty(raw_entry):
            continue
        if not isinstance(raw_entry, Mapping):
            warnings.append(
                f"{prefix}: {quote_value(raw_entry)} is not an entry; dropped"
            )
            continue
        dated = _partial_dates(raw_entry, prefix, warnings)
        entry: dict[str, Any] = schema.load(dated)  # pyright: ignore[reportAssignmentType]
        warnings.extend(describe_changes(dated, entry, prefix))
        if entry:
            entries.append(entry)
    return entries


def _string_tags(raw: dict[str, Any], warnings: list[str]) -> None:
    """Keep only the tags that are strings; anything else is a warning."""
    tags = raw.get(TAGS_KEY)
    if not isinstance(tags, list | tuple | set | frozenset):
        return
    kept = [tag for tag in tags if isinstance(tag, str)]
    warnings.extend(
        f"{TAGS_KEY}: {quote_value(tag)} is not a string; dropped"
        for tag in tags
        if not isinstance(tag, str)
    )
    raw[TAGS_KEY] = kept


def load_model_with_warnings(
    reading_list: Mapping[str, Any], path: Path | None = None
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """
    Validate a list against the model, naming everything that does not fit.

    Each warning starts with the path of what was dropped or changed:
    ``start_year``, ``entries #3.series``. They are returned, not logged.
    """
    warnings: list[str] = []
    with readable_depth():
        raw = dict(clean_tree(unwrap(reading_list), warnings))
        _string_tags(raw, warnings)
        raw_entries = raw.pop(ENTRIES_KEY, None)
        schema = get_schema(ReadingListYamlSchema, path=path)
        with unlogged_drops():
            loaded: dict[str, Any] = schema.load({READING_LIST_KEY: raw})  # pyright: ignore[reportAssignmentType]
            header = dict(loaded.get(READING_LIST_KEY) or {})
            warnings.extend(describe_changes(raw, header))
            if entries := _load_entries(raw_entries, warnings):
                header[ENTRIES_KEY] = entries
    return header, tuple(warnings)


def load_model(
    reading_list: Mapping[str, Any], path: Path | None = None
) -> dict[str, Any]:
    """Validate a list against the model, dropping what does not fit."""
    return load_model_with_warnings(reading_list, path)[0]


def resolve_format(
    text: str, fmt: ReadingListFormats | str | None = None
) -> ReadingListFormats:
    """
    Name the format given, else detect it, else raise with the reason.

    A YAML document that uses an alias is refused here, before anything
    parses or validates it whole.
    """
    with readable_depth():
        resolved = get_format(fmt) if fmt else detect_format(text)
        if resolved is None:
            reason = (
                syntax_error(text) or "Not a reading list in any format comicbox reads."
            )
            raise ReadingListFormatError(reason)
    if resolved.value.lexer == _YAML_LEXER:
        refuse_yaml_aliases(text)
    return resolved


def _decode(data: str | bytes | bytearray) -> tuple[str, bool]:
    """Decode bytes as UTF-8; say whether any had to be replaced."""
    if not isinstance(data, bytes | bytearray):
        return as_text(data), False
    try:
        return bytes(data).decode("utf-8-sig"), False
    except UnicodeDecodeError:
        return as_text(data), True


def _loads(
    data: str | bytes | bytearray,
    fmt: ReadingListFormats | str | None,
    path: Path | None,
) -> ReadingListResult:
    text, replaced = _decode(data)
    resolved = resolve_format(text, fmt)
    transform = resolved.value.transform_class(path)
    with readable_depth():
        document = transform.parse_data(data, text, replaced=replaced)
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
    """
    Read a reading list from a string or bytes, detecting its format.

    Bytes are UTF-8, except XML, which is read in the encoding it declares.
    """
    return _loads(data, fmt, None)


def load(
    path: Path | str, *, fmt: ReadingListFormats | str | None = None
) -> ReadingListResult:
    """Read a reading list from a file, detecting its format if not given."""
    path = Path(path)
    return _loads(path.read_bytes(), fmt, path)


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
