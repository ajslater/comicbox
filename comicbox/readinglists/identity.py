"""
Identity: when two reading-list entries are the same issue.

``entry_keys`` is the one definition. ``combine``, ``compare``, the CLI
matcher and codex's database matcher all use it, so they agree on what
counts as the same issue.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.fields.fields import IssueField
from comicbox.formats.base.online.signals import (
    normalize_series as _normalize_series,
)
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    DAY_KEY,
    ISSUE_SUFFIX_KEY,
    MONTH_KEY,
    SERIES_START_YEAR_KEY,
    YEAR_KEY,
)
from comicbox.identifiers import (
    DEFAULT_ID_TYPE,
    ID_KEY_KEY,
    ID_TYPE_KEY,
    ranked_id_sources,
)
from comicbox.readinglists.schema import (
    DATE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    SERIES_KEY,
    VOLUME_KEY,
)

# The online matcher's series rule, so every matcher compares names alike.
normalize_series = _normalize_series

# The first element of every key says which kind it is.
ID_KEY_KIND = "id"
NAME_KEY_KIND = "name"

EntryKey = tuple[Any, ...]

# Barcodes are spelled with and without separators; compare their digits.
_BARCODE_SOURCES = frozenset(
    {IdSources.GTIN.value, IdSources.ISBN.value, IdSources.UPC.value}
)
# A comic's UPC is 12 digits that name the title, the same on every issue,
# plus a 5-digit supplement for the issue, cover and printing. Only with the
# supplement does it name one issue. An ISBN or an ASIN names one book.
_SERIES_WIDE_BARCODE_SOURCES = frozenset({IdSources.GTIN.value, IdSources.UPC.value})
_SERIES_WIDE_BARCODE_MAX_DIGITS = 13


@dataclass(frozen=True, slots=True)
class ParsedIssue:
    """An issue name, normalized, and the number and suffix read out of it."""

    name: str
    number: Decimal | None
    suffix: str


def _to_decimal(text: str) -> Decimal | None:
    if not text.strip("."):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_issue(text: Any) -> ParsedIssue:
    """
    Normalize an issue name and split it into its number and suffix.

    The comicbox rules: ``#004AU`` is ``4AU``, number 4 and suffix ``AU``;
    ``½`` is ``.5``. ``3`` and ``3.0`` have equal numbers.
    """
    name = IssueField.parse_issue(str(text).strip()) if text is not None else ""
    number, suffix = IssueField.split_issue(name)
    return ParsedIssue(name, _to_decimal(number), suffix.strip())


def _issue_parts(entry: Mapping[str, Any]) -> tuple[Decimal | None, str] | None:
    """Get the issue's number and lowercased suffix, or None with no issue."""
    issue = entry.get(ISSUE_KEY) or {}
    if name := issue.get(NAME_KEY):
        parsed = parse_issue(name)
        number, suffix = parsed.number, parsed.suffix
    else:
        raw_number = issue.get(NUMBER_KEY)
        number = None if raw_number is None else _to_decimal(str(raw_number))
        suffix = str(issue.get(ISSUE_SUFFIX_KEY) or "").strip()
    if number is None and not suffix:
        return None
    return number, suffix.lower()


def _normalize_id_key(source: str, key: Any) -> str:
    """Normalize a key for comparing; empty when it does not name one issue."""
    key = str(key or "").strip()
    if source not in _BARCODE_SOURCES:
        return key
    key = "".join(char for char in key.upper() if char.isalnum())
    if (
        source in _SERIES_WIDE_BARCODE_SOURCES
        and sum(char.isdigit() for char in key) <= _SERIES_WIDE_BARCODE_MAX_DIGITS
    ):
        return ""
    return key


def _id_keys(entry: Mapping[str, Any]) -> Iterator[EntryKey]:
    """Issue ids, best ranked source first."""
    identifiers = entry.get(IDENTIFIERS_KEY) or {}
    for source in ranked_id_sources(identifiers):
        identifier = identifiers.get(source) or {}
        if (identifier.get(ID_TYPE_KEY) or DEFAULT_ID_TYPE) != DEFAULT_ID_TYPE:
            continue
        if key := _normalize_id_key(source, identifier.get(ID_KEY_KEY)):
            yield (ID_KEY_KIND, source, key)


def _discriminator(entry: Mapping[str, Any]) -> int | None:
    """Get the series start year or, failing that, the volume number."""
    series = entry.get(SERIES_KEY) or {}
    if (start_year := series.get(SERIES_START_YEAR_KEY)) is not None:
        return start_year
    volume = entry.get(VOLUME_KEY) or {}
    return volume.get(NUMBER_KEY)


def _name_key(entry: Mapping[str, Any]) -> EntryKey | None:
    """
    Build the key of the series, year or volume, number and suffix.

    None without a series name, an issue, or a start year or volume: a name
    and number alone match every volume of a long-running title, so such an
    entry joins by id only.
    """
    series = entry.get(SERIES_KEY) or {}
    if not (name := normalize_series(str(series.get(NAME_KEY) or ""))):
        return None
    if (issue := _issue_parts(entry)) is None:
        return None
    if (discriminator := _discriminator(entry)) is None:
        return None
    return (NAME_KEY_KIND, name, discriminator, *issue)


def entry_keys(entry: Mapping[str, Any]) -> tuple[EntryKey, ...]:
    """
    List the keys that identify an entry's issue, strongest first.

    ``("id", source, key)`` for each issue id, best ranked source first,
    then ``("name", series, start year or volume, number, suffix)``. Two
    entries are the same issue when they share a key.
    """
    keys = list(_id_keys(entry))
    if name_key := _name_key(entry):
        keys.append(name_key)
    return tuple(keys)


def entry_date(entry: Mapping[str, Any]) -> date | None:
    """Get the cover date, or the first day the year and month allow."""
    entry_date_ = entry.get(DATE_KEY) or {}
    if cover_date := entry_date_.get(COVER_DATE_KEY):
        return cover_date
    if not (year := entry_date_.get(YEAR_KEY)):
        return None
    try:
        return date(
            year, entry_date_.get(MONTH_KEY) or 1, entry_date_.get(DAY_KEY) or 1
        )
    except (TypeError, ValueError):
        return None


def entry_sort_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    """Sort by date, series and issue; anything missing sorts last."""
    when = entry_date(entry)
    series = entry.get(SERIES_KEY) or {}
    number, suffix = _issue_parts(entry) or (None, "")
    return (
        when is None,
        when or date.min,
        normalize_series(str(series.get(NAME_KEY) or "")),
        number is None,
        number or Decimal(0),
        suffix,
    )
