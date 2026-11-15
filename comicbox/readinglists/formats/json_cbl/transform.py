"""
Convert json-cbl 1.0 reading lists to and from the model.

json-cbl requires a series start year and a full cover date on every
issue, both ids of a database pair, and a UUID for the file and for each
relationship. An entry that lacks a start year or a cover year cannot be
written, and no year is invented to keep it: ``lost_fields`` names it.
"""

import re
import sys
import uuid
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any

import comicbox.readinglists.schema as model
from comicbox.enums.comicbox import IdSources
from comicbox.enums.maps.identifiers import get_id_source_by_alias
from comicbox.formats.comicbox import schema as comic
from comicbox.identifiers import ID_KEY_KEY
from comicbox.readinglists.formats.json_cbl.schema import (
    COVER_IMAGE_URLS_KEY,
    DESCRIPTION_KEY,
    END_YEAR_KEY,
    FILE_DETAILS_KEY,
    ID_KEY,
    IMPRINT_KEY,
    ISSUE_COVER_DATE_KEY,
    ISSUE_KEY,
    ISSUE_LIST_KEY,
    ISSUE_NUMBER_KEY,
    ISSUE_TYPE_KEY,
    LIST_DETAILS_KEY,
    NAME_KEY,
    NOTES_KEY,
    PUBLISHER_KEY,
    RELATIONSHIP_KEY,
    RELATIONSHIPS_KEY,
    SERIES_KEY,
    SERIES_NAME_KEY,
    SERIES_START_YEAR_KEY,
    SOURCE_KEY,
    START_YEAR_KEY,
    TAGS_KEY,
    TYPE_KEY,
    URL_KEY,
    UUID_KEY,
    VERSION_KEY,
    JsonCblSchema,
)
from comicbox.readinglists.identity import entry_date
from comicbox.readinglists.schema import (
    SOURCE_CURATOR_KEY,
    SOURCE_CURATOR_URL_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_URL_KEY,
    SourceKind,
)
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

FORMAT_VERSION = Decimal("1.0")
_MAJOR_VERSION = 1
# json-cbl's bounds for every year it holds.
MIN_YEAR = 1900
MAX_YEAR = 2100
_HTTP_URL_RE = re.compile(r"^https?://")
_METRON_SOURCE_NAME = "Metron"

# json-cbl relationship -> model list reference.
_RELATIONSHIPS = MappingProxyType(
    {"previous": model.PREVIOUS_KEY, "following": model.NEXT_KEY}
)
# json-cbl type -> model list type, where Metron spells it otherwise.
_LIST_TYPES_READ = MappingProxyType({"team": "teams", "character": "characters"})
# Model list type -> json-cbl type. Writing "event" as "universal" is a
# judgement: the spec's universe-wide crossover is the nearest thing to
# Metron's event.
_LIST_TYPES = MappingProxyType(
    {
        "master": "master",
        "interuniversal": "interuniversal",
        "universal": "universal",
        "event": "universal",
        "teams": "team",
        "characters": "character",
        "story": "story",
    }
)
_ISSUE_TYPES_READ = MappingProxyType(
    {
        "Event Core": "core",
        "Event Tie-In": "tie-in",
        "Event One Shot": "one-shot",
        "Ongoing": "ongoing",
    }
)
_ISSUE_TYPES_WRITE = MappingProxyType(
    {entry_type: issue_type for issue_type, entry_type in _ISSUE_TYPES_READ.items()}
)
# json-cbl id name -> comicbox id source.
_ID_SOURCES = MappingProxyType(
    {
        "comicvine": IdSources.COMICVINE.value,
        "metron": IdSources.METRON.value,
        "grandComicsDatabase": IdSources.GCD.value,
    }
)
_ID_NAMES = MappingProxyType({source: name for name, source in _ID_SOURCES.items()})
# Curator codes and full names, as mokkari's AttributionSource lists them.
CURATORS = MappingProxyType(
    {
        "cbro": "Comic Book Reading Orders",
        "cmro": "Complete Marvel Reading Orders",
        "cbh": "Comic Book Herald",
        "cbt": "Comic Book Treasury",
        "mg": "Marvel Guides",
        "htlc": "How To Love Comics",
        "locg": "League of ComicGeeks",
        "other": "Other sources",
    }
)
_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]+")
_DROPPED_LIST_DETAILS = (PUBLISHER_KEY, IMPRINT_KEY, COVER_IMAGE_URLS_KEY)


def _fold(name: str) -> str:
    return _NON_ALPHANUM_RE.sub("", name.lower())


_CURATOR_CODES = MappingProxyType(
    {
        **{_fold(full_name): code for code, full_name in CURATORS.items()},
        **{code: code for code in CURATORS},
    }
)


def _read_list_type(value: Any) -> Any:
    """Spell a json-cbl list type as Metron does."""
    return _LIST_TYPES_READ.get(value, value) if isinstance(value, str) else value


def _curator_code(name: str) -> str:
    """Store a known curator as its code; keep any other name as given."""
    return _CURATOR_CODES.get(_fold(name), name)


def _http_url(url: Any) -> str:
    """Keep a URL only when it is one the spec allows."""
    url = str(url or "")
    return url if _HTTP_URL_RE.match(url) else ""


def _in_range(year: Any) -> bool:
    return isinstance(year, int) and MIN_YEAR <= year <= MAX_YEAR


def _start_year(entry: Mapping[str, Any]) -> int | None:
    """Get the series start year, or a volume number that is a year."""
    start_year = (entry.get(model.SERIES_KEY) or {}).get(comic.SERIES_START_YEAR_KEY)
    if _in_range(start_year):
        return start_year
    volume = (entry.get(model.VOLUME_KEY) or {}).get(model.NUMBER_KEY)
    return volume if _in_range(volume) else None


def _cover_date(entry: Mapping[str, Any]) -> str:
    """Write the cover date, or the first day the year and month allow."""
    when = entry_date(entry)
    return when.isoformat() if when else ""


def _writable(entry: Mapping[str, Any]) -> bool:
    """Whether an entry has everything json-cbl requires of an issue."""
    series = entry.get(model.SERIES_KEY) or {}
    return bool(
        series.get(model.NAME_KEY)
        and entry_issue_name(entry)
        and _start_year(entry) is not None
        and entry_date(entry) is not None
    )


class _Reader:
    """Read one json-cbl document, collecting warnings."""

    def __init__(self, warnings: list[str]) -> None:
        self._warnings = warnings

    def _ids(self, position: int, ids: Sequence[Mapping[str, Any]]) -> Iterator:
        """Yield ``(source, series id, issue id)`` per known database."""
        for item in ids:
            name = str(item.get(NAME_KEY) or "")
            source = _ID_SOURCES.get(name)
            if source is None and (id_source := get_id_source_by_alias(name, None)):
                source = id_source.value
            if source is None:
                self._warnings.append(f"Issue {position}: unknown id name {name!r}.")
                continue
            yield source, item.get(SERIES_KEY), item.get(ISSUE_KEY)

    def _identifiers(
        self, position: int, entry: dict[str, Any], ids: Sequence[Mapping[str, Any]]
    ) -> None:
        series_ids, issue_ids = {}, {}
        for source, series_key, issue_key in self._ids(position, ids):
            if series_key:
                series_ids[source] = {ID_KEY_KEY: series_key}
            if issue_key:
                issue_ids[source] = {ID_KEY_KEY: issue_key}
        if series_ids:
            entry[model.SERIES_KEY][model.IDENTIFIERS_KEY] = series_ids
        if issue_ids:
            entry[model.IDENTIFIERS_KEY] = issue_ids

    def issue(self, position: int, issue: Mapping[str, Any]) -> dict | None:
        """Read one issue, or skip it with a warning."""
        series_name, number = issue.get(SERIES_NAME_KEY), issue.get(ISSUE_NUMBER_KEY)
        if not series_name or not number:
            self._warnings.append(f"Issue {position}: no series or number; skipped.")
            return None
        entry: dict[str, Any] = {
            model.SERIES_KEY: {
                model.NAME_KEY: series_name,
                comic.SERIES_START_YEAR_KEY: issue.get(SERIES_START_YEAR_KEY),
            },
            model.ISSUE_KEY: {model.NAME_KEY: number},
            model.DATE_KEY: {comic.COVER_DATE_KEY: issue.get(ISSUE_COVER_DATE_KEY)},
        }
        if issue_type := issue.get(ISSUE_TYPE_KEY):
            entry[model.ENTRY_TYPE_KEY] = _ISSUE_TYPES_READ.get(issue_type, issue_type)
        self._identifiers(position, entry, issue.get(ID_KEY) or ())
        return entry

    def sources(
        self, file_uuid: Any, items: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Read the file's own source, its curator and a Metron pointer."""
        source: dict[str, Any] = {SOURCE_KIND_KEY: SourceKind.JSON_CBL.value}
        if file_uuid:
            source[SOURCE_KEY_KEY] = file_uuid
        sources = [source]
        for item in items:
            name = str(item.get(NAME_KEY) or "")
            if _fold(name) == _fold(_METRON_SOURCE_NAME) and item.get(ID_KEY):
                pointer = {
                    SOURCE_KIND_KEY: SourceKind.METRON_LIST.value,
                    SOURCE_KEY_KEY: item[ID_KEY],
                    SOURCE_URL_KEY: item.get(URL_KEY),
                }
                sources.append(pointer)
            elif SOURCE_CURATOR_KEY not in source and name:
                source[SOURCE_CURATOR_KEY] = _curator_code(name)
                source[SOURCE_CURATOR_URL_KEY] = item.get(URL_KEY)
            else:
                self._warnings.append(f"Source {name!r} dropped.")
        return sources

    def relationships(self, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Read the previous and following lists."""
        refs: dict[str, Any] = {}
        for item in items:
            key = _RELATIONSHIPS.get(str(item.get(RELATIONSHIP_KEY)))
            if key is None or key in refs:
                self._warnings.append(f"Relationship {item.get(NAME_KEY)!r} dropped.")
                continue
            refs[key] = {
                model.NAME_KEY: item.get(NAME_KEY),
                SOURCE_KIND_KEY: SourceKind.JSON_CBL.value,
                SOURCE_KEY_KEY: item.get(UUID_KEY),
            }
        return refs

    def check(self, data: Mapping[str, Any]) -> None:
        """Warn of a newer major version and of fields the model lacks."""
        version = (data.get(FILE_DETAILS_KEY) or {}).get(VERSION_KEY)
        if version is not None and int(version) != _MAJOR_VERSION:
            self._warnings.append(f"json-cbl version {version} read as 1.0.")
        details = data.get(LIST_DETAILS_KEY) or {}
        if dropped := [key for key in _DROPPED_LIST_DETAILS if details.get(key)]:
            self._warnings.append(
                f"listDetails {', '.join(dropped)} dropped: the model has no place."
            )


class _Writer:
    """Write one reading list as a json-cbl document."""

    def __init__(self, reading_list: Mapping[str, Any]) -> None:
        self._reading_list = reading_list

    def file_uuid(self) -> str:
        """Get the list's json-cbl UUID, or mint a new one."""
        for source in self._reading_list.get(model.SOURCES_KEY) or ():
            if source.get(SOURCE_KIND_KEY) == SourceKind.JSON_CBL.value and (
                key := source.get(SOURCE_KEY_KEY)
            ):
                return str(key)
        return str(uuid.uuid4())

    def _sources(self) -> list[dict[str, str]]:
        items = []
        for source in self._reading_list.get(model.SOURCES_KEY) or ():
            if curator := source.get(SOURCE_CURATOR_KEY):
                item = {NAME_KEY: CURATORS.get(curator, curator)}
                url = source.get(SOURCE_CURATOR_URL_KEY) or source.get(SOURCE_URL_KEY)
                if url := _http_url(url):
                    item[URL_KEY] = url
                items.append(item)
            if source.get(SOURCE_KIND_KEY) == SourceKind.METRON_LIST.value and (
                key := source.get(SOURCE_KEY_KEY)
            ):
                item = {NAME_KEY: _METRON_SOURCE_NAME, ID_KEY: str(key)}
                if url := _http_url(source.get(SOURCE_URL_KEY)):
                    item[URL_KEY] = url
                items.append(item)
        return items

    def _relationships(self) -> list[dict[str, str]]:
        items = []
        for relationship, key in _RELATIONSHIPS.items():
            ref = self._reading_list.get(key) or {}
            if ref.get(SOURCE_KIND_KEY) == SourceKind.JSON_CBL.value and (
                ref_uuid := ref.get(SOURCE_KEY_KEY)
            ):
                items.append(
                    {
                        NAME_KEY: ref.get(model.NAME_KEY) or "",
                        UUID_KEY: ref_uuid,
                        RELATIONSHIP_KEY: relationship,
                    }
                )
        return items

    def list_details(self) -> dict[str, Any]:
        """Write the header."""
        reading_list = self._reading_list
        details: dict[str, Any] = {
            NAME_KEY: reading_list.get(model.NAME_KEY) or "",
            DESCRIPTION_KEY: reading_list.get(model.DESCRIPTION_KEY),
            TYPE_KEY: _LIST_TYPES.get(reading_list.get(model.LIST_TYPE_KEY, "")),
            TAGS_KEY: sorted(reading_list.get(model.TAGS_KEY) or ()),
            RELATIONSHIPS_KEY: self._relationships(),
            SOURCE_KEY: self._sources(),
        }
        for model_key, key in (
            (model.START_YEAR_KEY, START_YEAR_KEY),
            (model.END_YEAR_KEY, END_YEAR_KEY),
        ):
            if _in_range(year := reading_list.get(model_key)):
                details[key] = year
        return details

    @staticmethod
    def _ids(entry: Mapping[str, Any]) -> list[dict[str, str]]:
        """Write each database whose series and issue ids are both known."""
        items = []
        for source, name in _ID_NAMES.items():
            if (series_key := series_id(entry, source)) and (
                issue_key := issue_id(entry, source)
            ):
                items.append(
                    {NAME_KEY: name, SERIES_KEY: series_key, ISSUE_KEY: issue_key}
                )
        return items

    @classmethod
    def issue(cls, entry: Mapping[str, Any]) -> dict[str, Any]:
        """Write one writable entry."""
        return {
            SERIES_NAME_KEY: entry[model.SERIES_KEY][model.NAME_KEY],
            SERIES_START_YEAR_KEY: _start_year(entry),
            ISSUE_NUMBER_KEY: entry_issue_name(entry),
            ISSUE_COVER_DATE_KEY: _cover_date(entry),
            ISSUE_TYPE_KEY: _ISSUE_TYPES_WRITE.get(entry.get(model.ENTRY_TYPE_KEY, "")),
            ID_KEY: cls._ids(entry),
        }


class JsonCblTransform(ReadingListTransform):
    """json-cbl 1.0."""

    SCHEMA_CLASS = JsonCblSchema

    @override
    def to_reading_list(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Read a json-cbl document. It is ordered by definition."""
        reader = _Reader(self.warnings)
        reader.check(data)
        file_details = data.get(FILE_DETAILS_KEY) or {}
        details = data.get(LIST_DETAILS_KEY) or {}
        issues = data.get(ISSUE_LIST_KEY) or ()
        return {
            model.NAME_KEY: details.get(NAME_KEY),
            model.DESCRIPTION_KEY: details.get(DESCRIPTION_KEY),
            model.LIST_TYPE_KEY: _read_list_type(details.get(TYPE_KEY)),
            model.ORDERED_KEY: True,
            model.START_YEAR_KEY: details.get(START_YEAR_KEY),
            model.END_YEAR_KEY: details.get(END_YEAR_KEY),
            model.SOURCES_KEY: reader.sources(
                file_details.get(UUID_KEY), details.get(SOURCE_KEY) or ()
            ),
            **reader.relationships(details.get(RELATIONSHIPS_KEY) or ()),
            model.TAGS_KEY: details.get(TAGS_KEY),
            model.NOTES_KEY: data.get(NOTES_KEY),
            model.ENTRIES_KEY: [
                entry
                for position, issue in enumerate(issues, start=1)
                if (entry := reader.issue(position, issue)) is not None
            ],
        }

    @override
    def from_reading_list(self, reading_list: Mapping[str, Any]) -> dict[str, Any]:
        """Write a json-cbl document of the entries it can carry."""
        writer = _Writer(reading_list)
        entries = reading_list.get(model.ENTRIES_KEY) or ()
        return {
            FILE_DETAILS_KEY: {
                VERSION_KEY: FORMAT_VERSION,
                UUID_KEY: writer.file_uuid(),
            },
            LIST_DETAILS_KEY: writer.list_details(),
            NOTES_KEY: reading_list.get(model.NOTES_KEY),
            ISSUE_LIST_KEY: [
                writer.issue(entry) for entry in entries if _writable(entry)
            ],
        }

    @override
    def unwritable(self, reading_list: Mapping[str, Any]) -> tuple[int, ...]:
        """List the entries without a series, issue, start year or year."""
        entries = reading_list.get(model.ENTRIES_KEY) or ()
        return tuple(
            index for index, entry in enumerate(entries) if not _writable(entry)
        )
