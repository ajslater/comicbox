"""
Base class for converting a format's document to and from the model.

A sibling of ``BaseTransform``, not a subclass. ``BaseTransform`` compiles
glom keypath specs and loads its result as a comic; a reading list is a
list of nested rows, so each format converts with builder functions, and
the result is a reading list.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any
from xml.parsers.expat import ExpatError

from ruamel.yaml.error import YAMLError

from comicbox.empty import is_empty
from comicbox.exceptions import ReadingListFormatError
from comicbox.formats.base.schemas.base import BaseSchema
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.comicbox.schema import ISSUE_SUFFIX_KEY
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_KEY_KEY, ID_TYPE_KEY
from comicbox.readinglists.schema import (
    ENTRIES_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    ORDERED_KEY,
    PRIVATE_KEY,
    SERIES_KEY,
    ReadingListYamlSchema,
)

# What the render modules raise for text they cannot parse: simplejson's
# JSONDecodeError is a ValueError, ruamel's errors are YAMLErrors and
# xmltodict lets expat's through.
_PARSE_ERRORS = (ValueError, YAMLError, ExpatError)
_ENTRIES_PREFIX = f"{ENTRIES_KEY}."
# Flags whose default a format loses nothing by dropping.
_FLAG_DEFAULTS = MappingProxyType({ORDERED_KEY: True, PRIVATE_KEY: False})


def _get_path(data: Any, keys: tuple[str, ...]) -> Any:
    """Get a nested value, or None when any step is missing."""
    for key in keys:
        if not isinstance(data, Mapping):
            return None
        data = data.get(key)
    return data


def issue_id(entry: Mapping[str, Any], source: str) -> str:
    """Get an entry's issue id for a database, ignoring other id types."""
    identifier = (entry.get(IDENTIFIERS_KEY) or {}).get(source) or {}
    if (identifier.get(ID_TYPE_KEY) or DEFAULT_ID_TYPE) != DEFAULT_ID_TYPE:
        return ""
    return str(identifier.get(ID_KEY_KEY) or "")


def series_id(entry: Mapping[str, Any], source: str) -> str:
    """Get an entry's series id for a database."""
    series = entry.get(SERIES_KEY) or {}
    identifier = (series.get(IDENTIFIERS_KEY) or {}).get(source) or {}
    return str(identifier.get(ID_KEY_KEY) or "")


def entry_issue_name(entry: Mapping[str, Any]) -> str:
    """Get an entry's issue name, or build it from the number and suffix."""
    issue = entry.get(ISSUE_KEY) or {}
    if name := issue.get(NAME_KEY):
        return str(name)
    number = issue.get(NUMBER_KEY)
    number = "" if number is None else number
    return f"{number}{issue.get(ISSUE_SUFFIX_KEY) or ''}".strip()


def skipped_entries(positions: Iterable[int]) -> str:
    """Name the entries a write has to leave out, by position."""
    return f"{ENTRIES_KEY}[{', '.join(str(position) for position in positions)}]"


def _is_used(keypath: str, value: Any) -> bool:
    """Whether a value carries anything: not empty, and not a flag's default."""
    if keypath in _FLAG_DEFAULTS and value == _FLAG_DEFAULTS[keypath]:
        return False
    return not is_empty(value)


class ReadingListTransform:
    """
    Convert one format's document to and from the reading-list model.

    One instance serves one call. ``warnings`` collects what the call had
    to drop or guess, for the caller to show; the library does not log
    them.
    """

    SCHEMA_CLASS: type[BaseSchema] = ReadingListYamlSchema
    # Model keypaths this format cannot carry. Entry keys are prefixed with
    # ``entries.``. ``losses`` reports the ones a list actually uses.
    LOSSY_KEYS: frozenset[str] = frozenset()

    def __init__(self, path: Path | str | None = None) -> None:
        """Get the schema and start an empty warnings list."""
        self._path = path
        self._schema: BaseSchema = get_schema(self.SCHEMA_CLASS, path=path)
        self.warnings: list[str] = []

    @property
    def root_tag(self) -> str:
        """The root tag of this format's documents."""
        return self._schema.ROOT_TAG

    def parse(self, text: str) -> dict[str, Any]:
        """Parse text into a document loaded through this format's schema."""
        try:
            document = self._schema.opts.render_module.loads(text)
        except _PARSE_ERRORS as exc:
            reason = f"Cannot parse the document: {exc}"
            raise ReadingListFormatError(reason) from exc
        if not isinstance(document, Mapping) or self.root_tag not in document:
            reason = f"No '{self.root_tag}' root found."
            raise ReadingListFormatError(reason)
        loaded: dict[str, Any] = self._schema.load(document)  # pyright: ignore[reportAssignmentType]
        if not loaded:
            reason = f"Nothing readable under '{self.root_tag}'."
            raise ReadingListFormatError(reason)
        return loaded

    def render(self, document: Mapping[str, Any]) -> str:
        """Serialize a document with this format's schema."""
        return self._schema.dumps(document)

    def to_reading_list(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Convert a parsed document to the model's inner mapping."""
        return dict(data.get(self.root_tag) or {})

    def from_reading_list(self, reading_list: Mapping[str, Any]) -> dict[str, Any]:
        """Convert the model's inner mapping to a document for this format."""
        return {self.root_tag: dict(reading_list)}

    @staticmethod
    def _uses(reading_list: Mapping[str, Any], keypath: str) -> bool:
        """Whether the list, or any of its entries, uses a keypath."""
        if keypath.startswith(_ENTRIES_PREFIX):
            keys = tuple(keypath.removeprefix(_ENTRIES_PREFIX).split("."))
            entries = reading_list.get(ENTRIES_KEY) or ()
            return any(_is_used(keypath, _get_path(entry, keys)) for entry in entries)
        return _is_used(keypath, _get_path(reading_list, tuple(keypath.split("."))))

    def losses(self, reading_list: Mapping[str, Any]) -> tuple[str, ...]:
        """List the model keypaths writing this list in this format would drop."""
        return tuple(
            keypath
            for keypath in sorted(self.LOSSY_KEYS)
            if self._uses(reading_list, keypath)
        )
