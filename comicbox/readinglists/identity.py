"""
Identity: when two reading-list entries are the same issue.

``entry_keys`` is the one definition. ``combine``, ``compare``, the CLI
matcher and codex's database matcher all use it, so they agree on what
counts as the same issue.
"""

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from comicbox.enums.comicbox import IdSources
from comicbox.formats.base.fields.fields import IssueField
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
from comicbox.series_name import normalize_series

# The first element of every key says which kind it is.
ID_KEY_KIND = "id"
NAME_KEY_KIND = "name"
NAME_YEAR_KEY_KIND = "name-year"

EntryKey = tuple[Any, ...]

# A barcode names a cover, a printing or an edition of an issue, not the
# issue: a shared one finds a match, and a differing one never vetoes one, in
# combine as in the matcher.
BARCODE_ID_SOURCES = frozenset(
    {
        IdSources.ASIN.value,
        IdSources.GTIN.value,
        IdSources.ISBN.value,
        IdSources.UPC.value,
    }
)
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
    ``½`` is ``.5``. ``3`` and ``3.0`` have equal numbers. ``-1`` is a real
    issue number: ``IssueField.split_issue`` reads its sign.
    """
    name = IssueField.parse_issue(str(text).strip()) if text is not None else ""
    number_text, suffix = IssueField.split_issue(name)
    return ParsedIssue(name, _to_decimal(number_text), suffix.strip())


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


def _series_issue(
    entry: Mapping[str, Any],
) -> tuple[str, tuple[Decimal | None, str]] | None:
    """Get the normalized series name and the issue, or None without both."""
    series = entry.get(SERIES_KEY) or {}
    if not (name := normalize_series(str(series.get(NAME_KEY) or ""))):
        return None
    if (issue := _issue_parts(entry)) is None:
        return None
    return name, issue


# A volume number this big is a year, as a CBL's Volume="2006" is.
YEAR_LIKE_VOLUME = 1900


def _differ(one: int | None, other: int | None) -> bool:
    return one is not None and other is not None and one != other


@dataclass(frozen=True, slots=True)
class Discriminators:
    """
    What a row tells its volume by: up to one discriminator of each kind.

    ``year`` is the year-like one: the start year or, failing that, a volume
    number of 1900 or more, as a CBL's ``Volume="2006"`` is. ``volume`` is a
    volume number under 1900. Z-Men (1991) volume 2 has both.
    """

    year: int | None = None
    volume: int | None = None

    def shares_a_kind(self, other: "Discriminators") -> bool:
        """Tell whether two rows have a discriminator of one kind each."""
        return (self.year is not None and other.year is not None) or (
            self.volume is not None and other.volume is not None
        )

    def conflicts(self, other: "Discriminators") -> bool:
        """
        Tell whether two rows are of two volumes.

        They conflict when they have a discriminator of the same kind and
        those differ, in either kind: the 2011 and 2016 volumes, or volumes 1
        and 2. A start year and volume 2 cannot be compared.
        """
        return _differ(self.year, other.year) or _differ(self.volume, other.volume)


def _whole_number(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def discriminators(entry: Mapping[str, Any]) -> Discriminators:
    """Get what an entry tells its volume by."""
    series = entry.get(SERIES_KEY) or {}
    start_year = _whole_number(series.get(SERIES_START_YEAR_KEY))
    number = _whole_number((entry.get(VOLUME_KEY) or {}).get(NUMBER_KEY))
    if number is not None and number < YEAR_LIKE_VOLUME:
        return Discriminators(start_year, number)
    return Discriminators(number if start_year is None else start_year)


# Which discriminator a name key holds; volume 2 is not year 2.
YEAR_DISCRIMINATOR = "year"
VOLUME_DISCRIMINATOR = "volume"


def _name_keys(entry: Mapping[str, Any]) -> tuple[EntryKey, ...]:
    """
    Build a key of the series, discriminator, number and suffix per kind.

    The year key, by the start year or a year-like volume, comes before the
    volume key, by a volume number under 1900. None without a series name,
    an issue, and a discriminator: a name and number alone match every volume
    of a long-running title.
    """
    if (named := _series_issue(entry)) is None:
        return ()
    name, issue = named
    value = discriminators(entry)
    return tuple(
        (NAME_KEY_KIND, name, kind, discriminator, *issue)
        for kind, discriminator in (
            (YEAR_DISCRIMINATOR, value.year),
            (VOLUME_DISCRIMINATOR, value.volume),
        )
        if discriminator is not None
    )


def any_conflict(values: Iterable[Discriminators]) -> bool:
    """Tell whether any two of some rows' discriminators conflict."""
    values = tuple(values)
    years = {value.year for value in values if value.year is not None}
    volumes = {value.volume for value in values if value.volume is not None}
    return len(years) > 1 or len(volumes) > 1


def _cover_year(entry: Mapping[str, Any]) -> int | None:
    """Get the cover year: ``date.year``, or the year of ``date.cover_date``."""
    entry_date_ = entry.get(DATE_KEY) or {}
    year = entry_date_.get(YEAR_KEY)
    if isinstance(year, int) and not isinstance(year, bool):
        return year
    cover_date = entry_date_.get(COVER_DATE_KEY)
    return cover_date.year if isinstance(cover_date, date) else None


def _name_year_key(entry: Mapping[str, Any]) -> EntryKey | None:
    """
    Build the weakest key: the series, the cover year, number and suffix.

    For every entry with a series name, an issue and a cover year, so a row
    with a year and no volume, as a CBL often has, meets a row that has a
    start year. Two volumes whose issues share a number and a cover year
    share this key too: ``Discriminators.conflicts`` tells them apart
    where it can.
    """
    if (named := _series_issue(entry)) is None:
        return None
    if (year := _cover_year(entry)) is None:
        return None
    name, issue = named
    return (NAME_YEAR_KEY_KIND, name, year, *issue)


# A trailing year or volume in parentheses: "Bladehawk (2016)", "X (Vol. 2)",
# "X (v2)", "X (Volume 2)". Not "Trundlebots (UK)": that names another
# series. No leading whitespace run, which would make a run of spaces
# quadratic; the name is stripped after.
_TRAILING_YEAR_OR_VOLUME_RE = re.compile(
    r"\(\s*(?:\d{4}|v(?:ol(?:ume)?)?\.?\s*\d+)\s*\)\s*$", re.IGNORECASE
)
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|an|a)\s+", re.IGNORECASE)
# Collected-edition words that end a series name, normalized.
_REPRINT_SUFFIXES = (
    "trade paperback",
    "deluxe edition",
    "hardcover",
    "omnibus",
    "tpb",
    "hc",
)


def _without_reprint_suffix(normalized: str) -> str:
    for suffix in _REPRINT_SUFFIXES:
        if normalized.endswith(f" {suffix}"):
            return normalized.removesuffix(f" {suffix}")
    return normalized


# The same words, as a raw name spells them, to take off before its year.
_REPRINT_SUFFIX_WORDS = tuple(tuple(suffix.split()) for suffix in _REPRINT_SUFFIXES)


def _without_reprint_suffix_words(raw: str) -> str:
    """Take a reprint suffix off a raw name, by its words: linear in the name."""
    words = raw.split()
    folded = tuple(word.casefold() for word in words)
    for suffix in _REPRINT_SUFFIX_WORDS:
        if len(words) > len(suffix) and folded[-len(suffix) :] == suffix:
            return " ".join(words[: -len(suffix)])
    return raw


def _without_year_or_volume(raw: str) -> str:
    match = _TRAILING_YEAR_OR_VOLUME_RE.search(raw)
    return raw[: match.start()].rstrip() if match else raw


def _without_article(raw: str) -> str:
    return _LEADING_ARTICLE_RE.sub("", raw, count=1)


# Each step is taken from every spelling before it, in this order, so they
# compose: "The Bladehawk (2016) TPB" comes to "Bladehawk".
_SPELLING_STEPS = (
    _without_reprint_suffix_words,
    _without_year_or_volume,
    _without_article,
)


def name_variants(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """
    List the series names to try for an entry, normalized, in order.

    The name as given; then the name without a reprint suffix such as TPB or
    Omnibus, without a trailing year or volume in parentheses
    (``Bladehawk (2016)``, ``X (Vol. 2)``), and without a leading article,
    each step taken from every spelling before it, so they compose: ``The
    Bladehawk (2016) TPB`` comes to ``bladehawk``. A year or volume is never
    added: ``Ivory Knight`` is not the series ``Ivory Knight 2020``. For
    matching a list against comics only: ``entry_keys`` stays strict, so
    ``combine`` never joins on a variant.
    """
    raw = str((entry.get(SERIES_KEY) or {}).get(NAME_KEY) or "").strip()
    if not raw:
        return ()
    normalized = [normalize_series(name) for name in _spelled_variants(raw)]
    normalized += [_without_reprint_suffix(name) for name in normalized]
    return tuple(dict.fromkeys(name for name in normalized if name))


def _spelled_variants(raw: str) -> list[str]:
    """Spell the name as given, then with each step taken from every spelling."""
    names = [raw]
    for step in _SPELLING_STEPS:
        names += [spelled for name in names if (spelled := step(name)) != name]
    return names


def variant_keys(entry: Mapping[str, Any]) -> tuple[EntryKey, ...]:
    """
    Build the name keys of an entry's variants, its own name key first.

    Each keeps one of the entry's discriminators and its issue, so an entry
    with no name key has no variants either: it still matches by id alone.
    For each name, the year key comes before the volume key.
    """
    return tuple(
        (NAME_KEY_KIND, name, *rest)
        for name in name_variants(entry)
        for _, _, *rest in _name_keys(entry)
    )


def entry_keys(entry: Mapping[str, Any]) -> tuple[EntryKey, ...]:
    """
    List the keys that identify an entry's issue, strongest first.

    ``("id", source, key)`` for each issue id, best ranked source first,
    then ``("name", series, "year", year, number, suffix)`` by the start
    year or a year-like volume, then ``("name", series, "volume", volume,
    number, suffix)`` by a volume number under 1900, then the weakest,
    ``("name-year", series, cover year, number, suffix)``. Two entries are
    the same issue when they share a key and their discriminators do not
    conflict (``Discriminators.conflicts``): Z-Men (1963) and Z-Men (1991)
    may both be volume 1. An entry with none, no id and no series and issue
    with a start year, volume or cover year, matches nothing.
    """
    keys = [*_id_keys(entry), *_name_keys(entry)]
    if (name_year_key := _name_year_key(entry)) is not None:
        keys.append(name_year_key)
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
