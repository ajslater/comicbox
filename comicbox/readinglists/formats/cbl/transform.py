"""
Convert ComicRack ``.cbl`` reading lists to and from the model.

Tolerant on read: one bad row is skipped with a warning and the rest load,
since rejecting a whole file for one row is a standing complaint about
other readers.
"""

import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from xml.parsers.expat import ExpatError

import xmltodict

from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.exceptions import ReadingListFormatError, SmartListError
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    SERIES_START_YEAR_KEY,
    YEAR_KEY,
)
from comicbox.identifiers import ID_KEY_KEY
from comicbox.readinglists.changes import quote_value
from comicbox.readinglists.formats.cbl.schema import (
    BOOK_TAG,
    BOOKS_TAG,
    DATABASE_TAG,
    ISSUE_ATTR,
    MATCHERS_TAG,
    NAME_ATTR,
    NAME_TAG,
    NUM_ISSUES_TAG,
    NUMBER_ATTR,
    SERIES_ATTR,
    SOURCE_TAG,
    START_YEAR_TAG,
    VOLUME_ATTR,
    YEAR_ATTR,
    CblSchema,
)
from comicbox.readinglists.schema import (
    DATE_KEY,
    ENTRIES_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    SERIES_KEY,
    SOURCE_CURATOR_KEY,
    SOURCE_KIND_KEY,
    SOURCES_KEY,
    START_YEAR_KEY,
    VOLUME_KEY,
    SourceKind,
)
from comicbox.readinglists.syntax import describe_syntax_error
from comicbox.readinglists.transform import (
    ReadingListTransform,
    entry_issue_name,
    issue_id,
    series_id,
)

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

# A Volume in this range is read as the series start year too, which is how
# the community files use it; native ComicRack files may hold a volume
# number there instead.
MIN_START_YEAR = 1900
MAX_START_YEAR = datetime.now(tz=UTC).year + 1

# ComicRack's Volume and Year for "not known".
UNKNOWN_NUMBER = -1
# ComicRack and community files write these; the model has no place for
# them, so they are left out on purpose and not worth a warning.
_IGNORED_KEYS = frozenset({"@xmlns:xsd", "@xmlns:xsi", "@Format", "Id", "FileName"})

# <Database Name> values. Local, not identifier aliases: "cv" in the global
# alias map would change how every tag's free text is parsed.
_DATABASE_SOURCES = MappingProxyType(
    {"cv": IdSources.COMICVINE.value, "metron": IdSources.METRON.value}
)
# The databases CBL carries, and the names written for them.
_DATABASE_NAMES = MappingProxyType(
    {IdSources.COMICVINE.value: "cv", IdSources.METRON.value: "metron"}
)


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _writable(entry: Mapping[str, Any]) -> bool:
    return bool((entry.get(SERIES_KEY) or {}).get(NAME_KEY) and entry_issue_name(entry))


def _entry_year(entry: Mapping[str, Any]) -> int | None:
    entry_date = entry.get(DATE_KEY) or {}
    if (year := entry_date.get(YEAR_KEY)) is not None:
        return year
    cover_date = entry_date.get(COVER_DATE_KEY)
    return cover_date.year if cover_date else None


def _volume(entry: Mapping[str, Any]) -> int | None:
    """Get the series start year or, failing that, the volume number."""
    start_year = (entry.get(SERIES_KEY) or {}).get(SERIES_START_YEAR_KEY)
    if start_year is not None:
        return start_year
    return (entry.get(VOLUME_KEY) or {}).get(NUMBER_KEY)


class CblTransform(ReadingListTransform):
    """ComicRack ``.cbl``."""

    SCHEMA_CLASS = CblSchema
    IGNORED_KEYS = _IGNORED_KEYS

    # Read

    @override
    def parse_data(
        self, data: str | bytes | bytearray, text: str, *, replaced: bool
    ) -> dict[str, Any]:
        """Parse XML from its bytes, so the encoding it declares is honoured."""
        if isinstance(data, bytes | bytearray):
            try:
                document = xmltodict.parse(bytes(data))
            except ExpatError as exc:
                if not replaced:
                    raise ReadingListFormatError(describe_syntax_error(exc)) from exc
                # Bytes not in the encoding they declare, or undeclared and
                # not UTF-8: read the text they were replaced in, and say so.
            else:
                return self.from_document(document)
        return super().parse_data(data, text, replaced=replaced)

    @override
    def load_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Keep an empty ``<Book />`` in its place, so positions count it."""
        books = (document.get(self.root_tag) or {}).get(BOOKS_TAG)
        if isinstance(books, dict) and BOOK_TAG in books:
            items = books[BOOK_TAG]
            items = items if isinstance(items, list) else [items]
            books[BOOK_TAG] = [{} if item is None else item for item in items]
        return super().load_document(document)

    def _database_ids(
        self, position: int, databases: Sequence[Mapping[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Read a book's series and issue ids from its databases."""
        series_ids: dict[str, Any] = {}
        issue_ids: dict[str, Any] = {}
        for database in databases:
            name = str(database.get(NAME_ATTR) or "").strip()
            source = _DATABASE_SOURCES.get(name.lower())
            if source is None and (id_source := get_id_source_by_alias(name, None)):
                source = id_source.value
            if source is None:
                self.warnings.append(
                    f"Book {position}: unknown database {quote_value(name)};"
                    " its ids are dropped."
                )
                continue
            if series_key := database.get(SERIES_ATTR):
                series_ids[source] = {ID_KEY_KEY: series_key}
            if issue_key := database.get(ISSUE_ATTR):
                issue_ids[source] = {ID_KEY_KEY: issue_key}
        return series_ids, issue_ids

    def _read_number(
        self, position: int, book: Mapping[str, Any], attr: str
    ) -> int | None:
        """
        Read a Volume or Year, or nothing.

        A negative number is no number: -1 is how ComicRack writes unknown,
        so it goes quietly, and any other is a warning, as is a non-number.
        """
        if (text := book.get(attr)) is None:
            return None
        number = _int(text)
        if number is not None and number >= 0:
            return number
        if number != UNKNOWN_NUMBER:
            self.warnings.append(
                f"Book {position}: {attr[1:]} {quote_value(text)} dropped."
            )
        return None

    def _read_numbers(
        self, position: int, book: Mapping[str, Any], entry: dict[str, Any]
    ) -> None:
        """Read Volume, also as a start year when it is one, and Year."""
        if (volume := self._read_number(position, book, VOLUME_ATTR)) is not None:
            entry[VOLUME_KEY] = {NUMBER_KEY: volume}
            if MIN_START_YEAR <= volume <= MAX_START_YEAR:
                entry[SERIES_KEY][SERIES_START_YEAR_KEY] = volume
        if (year := self._read_number(position, book, YEAR_ATTR)) is not None:
            entry[DATE_KEY] = {YEAR_KEY: year}

    def _read_book(self, position: int, book: Mapping[str, Any]) -> dict | None:
        """Read one book, or skip it with a warning."""
        series_name, number = book.get(SERIES_ATTR), book.get(NUMBER_ATTR)
        if not series_name or not number:
            self.warnings.append(f"Book {position}: no series or number; skipped.")
            return None
        entry: dict[str, Any] = {
            SERIES_KEY: {NAME_KEY: series_name},
            ISSUE_KEY: {NAME_KEY: number},
        }
        self._read_numbers(position, book, entry)
        databases = book.get(DATABASE_TAG) or ()
        series_ids, issue_ids = self._database_ids(position, databases)
        if series_ids:
            entry[SERIES_KEY][IDENTIFIERS_KEY] = series_ids
        if issue_ids:
            entry[IDENTIFIERS_KEY] = issue_ids
        return entry

    def _read_books(self, books: Sequence[Mapping[str, Any]]) -> Iterator[dict]:
        for position, book in enumerate(books, start=1):
            if (entry := self._read_book(position, book)) is not None:
                yield entry

    @override
    def to_reading_list(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Read a ``<ReadingList>``; a smart list raises."""
        root = data.get(self.root_tag) or {}
        if root.get(MATCHERS_TAG):
            reason = "A smart list: its <Matchers> select comics, they list none."
            raise SmartListError(reason)
        source = {SOURCE_KIND_KEY: SourceKind.FILE.value}
        if curator := root.get(SOURCE_TAG):
            source[SOURCE_CURATOR_KEY] = curator
        books = (root.get(BOOKS_TAG) or {}).get(BOOK_TAG) or ()
        reading_list = {
            NAME_KEY: root.get(NAME_TAG),
            START_YEAR_KEY: root.get(START_YEAR_TAG),
            SOURCES_KEY: [source],
            ENTRIES_KEY: list(self._read_books(books)),
        }
        return {key: value for key, value in reading_list.items() if value is not None}

    # Write

    @staticmethod
    def _databases(entry: Mapping[str, Any]) -> list[dict[str, str]]:
        databases = []
        for source, name in _DATABASE_NAMES.items():
            database = {NAME_ATTR: name}
            if series_key := series_id(entry, source):
                database[SERIES_ATTR] = series_key
            if issue_key := issue_id(entry, source):
                database[ISSUE_ATTR] = issue_key
            if len(database) > 1:
                databases.append(database)
        return databases

    @classmethod
    def _book(cls, entry: Mapping[str, Any]) -> dict[str, Any]:
        book: dict[str, Any] = {
            SERIES_ATTR: entry[SERIES_KEY][NAME_KEY],
            NUMBER_ATTR: entry_issue_name(entry),
        }
        if (volume := _volume(entry)) is not None:
            book[VOLUME_ATTR] = str(volume)
        if (year := _entry_year(entry)) is not None:
            book[YEAR_ATTR] = str(year)
        if databases := cls._databases(entry):
            book[DATABASE_TAG] = databases
        return book

    @override
    def from_reading_list(self, reading_list: Mapping[str, Any]) -> dict[str, Any]:
        """Write a ``<ReadingList>`` with a true ``<NumIssues>``."""
        entries = reading_list.get(ENTRIES_KEY) or ()
        books = [self._book(entry) for entry in entries if _writable(entry)]
        curator = next(
            (
                source[SOURCE_CURATOR_KEY]
                for source in reading_list.get(SOURCES_KEY) or ()
                if source.get(SOURCE_CURATOR_KEY)
            ),
            None,
        )
        root = {
            NAME_TAG: reading_list.get(NAME_KEY),
            NUM_ISSUES_TAG: len(books),
            START_YEAR_TAG: reading_list.get(START_YEAR_KEY),
            SOURCE_TAG: curator,
            BOOKS_TAG: {BOOK_TAG: books},
        }
        return {self.root_tag: root}

    # Losses

    @override
    def unwritable(self, reading_list: Mapping[str, Any]) -> tuple[int, ...]:
        """List the entries with no series name or issue: a Book needs both."""
        entries = reading_list.get(ENTRIES_KEY) or ()
        return tuple(
            index for index, entry in enumerate(entries) if not _writable(entry)
        )
