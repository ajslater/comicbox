"""
Base class for converting a format's document to and from the model.

A sibling of ``BaseTransform``, not a subclass. ``BaseTransform`` compiles
glom keypath specs and loads its result as a comic; a reading list is a
list of nested rows, so each format converts with builder functions, and
the result is a reading list.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

from ruamel.yaml.error import YAMLError

from comicbox.exceptions import ReadingListFormatError
from comicbox.formats.base.schemas.base import BaseSchema
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.base.schemas.error_store import unlogged_drops
from comicbox.formats.comicbox.schema import ISSUE_SUFFIX_KEY
from comicbox.identifiers import DEFAULT_ID_TYPE, ID_KEY_KEY, ID_TYPE_KEY
from comicbox.readinglists.changes import describe_changes
from comicbox.readinglists.schema import (
    ENTRIES_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NAME_KEY,
    NUMBER_KEY,
    SERIES_KEY,
    ReadingListYamlSchema,
)
from comicbox.readinglists.syntax import describe_syntax_error

# What the render modules raise for text they cannot parse: simplejson's
# JSONDecodeError is a ValueError, ruamel's errors are YAMLErrors and
# xmltodict lets expat's through.
_PARSE_ERRORS = (ValueError, YAMLError, ExpatError)
_ENTRIES_PREFIX = f"{ENTRIES_KEY}."


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


class ReadingListTransform:
    """
    Convert one format's document to and from the reading-list model.

    One instance serves one call. ``warnings`` collects what the call had
    to drop or guess, for the caller to show; the library does not log
    them.
    """

    SCHEMA_CLASS: type[BaseSchema] = ReadingListYamlSchema

    def __init__(self, path: Path | str | None = None) -> None:
        """Get the schema and start an empty warnings list."""
        self._path = path
        self._schema: BaseSchema = get_schema(self.SCHEMA_CLASS, path=path)
        self.warnings: list[str] = []

    @property
    def root_tag(self) -> str:
        """The root tag of this format's documents."""
        return self._schema.ROOT_TAG

    # Keys a format leaves out of its schema on purpose, so dropping them is
    # not worth a warning.
    IGNORED_KEYS: frozenset[str] = frozenset()

    def parse(self, text: str) -> dict[str, Any]:
        """Parse text, then load it through this format's schema."""
        try:
            document = self._schema.opts.render_module.loads(text)
        except _PARSE_ERRORS as exc:
            raise ReadingListFormatError(describe_syntax_error(exc)) from exc
        if not isinstance(document, Mapping) or self.root_tag not in document:
            reason = f"No '{self.root_tag}' root found."
            raise ReadingListFormatError(reason)
        loaded = self.load_document(document)
        if not loaded:
            reason = f"Nothing readable under '{self.root_tag}'."
            raise ReadingListFormatError(reason)
        return loaded

    def load_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Load a parsed document through the schema, naming what it drops."""
        with unlogged_drops():
            loaded: dict[str, Any] = self._schema.load(document)  # pyright: ignore[reportAssignmentType]
        self.warnings.extend(describe_changes(document, loaded, "", self.IGNORED_KEYS))
        return loaded

    def render(self, document: Mapping[str, Any]) -> str:
        """Serialize a document with this format's schema."""
        return self._schema.dumps(document)

    def to_reading_list(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Convert a parsed document to the model's inner mapping."""
        root = data.get(self.root_tag) or {}
        if not isinstance(root, Mapping):
            reason = f"'{self.root_tag}' holds {type(root).__name__}, not a list."
            raise ReadingListFormatError(reason)
        return dict(root)

    def from_reading_list(self, reading_list: Mapping[str, Any]) -> dict[str, Any]:
        """Convert the model's inner mapping to a document for this format."""
        return {self.root_tag: dict(reading_list)}

    def unwritable(self, reading_list: Mapping[str, Any]) -> tuple[int, ...]:
        """List the positions, from 0, of entries this format cannot write."""
        del reading_list
        return ()
