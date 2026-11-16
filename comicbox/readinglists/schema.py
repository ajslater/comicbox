"""
The comicbox reading-list model: key constants and schemas.

A reading list is a header plus ``entries``, and an entry is a comic
reference in comicbox's own vocabulary: its ``series``, ``volume``,
``issue``, ``date`` and ``identifiers`` are the comicbox sub-schemas, so an
entry is a valid fragment of a comicbox comic.

The value passed around the API is the inner mapping, the one under
``reading_list``. Only serialized documents carry the root key.
"""

import re
import sys
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from marshmallow import ValidationError
from marshmallow.fields import Constant, Nested

from comicbox.formats.base.fields.collection_fields import ListField, StringSetField
from comicbox.formats.base.fields.comicbox import SimpleNamedNestedField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import BooleanField, IntegerField
from comicbox.formats.base.fields.time_fields import DateField
from comicbox.formats.base.schemas.base import BaseSubSchema
from comicbox.formats.base.schemas.json_schemas import JsonSchema
from comicbox.formats.base.schemas.yaml import YamlRenderModule, YamlSchema
from comicbox.formats.comicbox.schema import DATE_KEY as _DATE_KEY
from comicbox.formats.comicbox.schema import IDENTIFIERS_KEY as _IDENTIFIERS_KEY
from comicbox.formats.comicbox.schema import ISSUE_KEY as _ISSUE_KEY
from comicbox.formats.comicbox.schema import NAME_KEY as _NAME_KEY
from comicbox.formats.comicbox.schema import NOTES_KEY as _NOTES_KEY
from comicbox.formats.comicbox.schema import NUMBER_KEY as _NUMBER_KEY
from comicbox.formats.comicbox.schema import SERIES_KEY as _SERIES_KEY
from comicbox.formats.comicbox.schema import TAGS_KEY as _TAGS_KEY
from comicbox.formats.comicbox.schema import VOLUME_KEY as _VOLUME_KEY
from comicbox.formats.comicbox.schema.identifiers import IdentifiedSchema
from comicbox.formats.comicbox.schema.publishing import (
    IssueSchema,
    SeriesSchema,
    VolumeSchema,
)

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


# The root tag of a serialized reading list.
READING_LIST_KEY = "reading_list"
READING_LIST_SCHEMA_ID = "https://github.com/ajslater/comicbox/blob/main/schemas/reading-list/v1.0/reading-list-v1.0.schema.json"

# Keys a reading list shares with a comic, re-exported so callers need only
# this package.
NAME_KEY = _NAME_KEY
TAGS_KEY = _TAGS_KEY
NOTES_KEY = _NOTES_KEY
SERIES_KEY = _SERIES_KEY
VOLUME_KEY = _VOLUME_KEY
ISSUE_KEY = _ISSUE_KEY
DATE_KEY = _DATE_KEY
IDENTIFIERS_KEY = _IDENTIFIERS_KEY
NUMBER_KEY = _NUMBER_KEY

# List header keys, beside NAME_KEY, TAGS_KEY and NOTES_KEY.
DESCRIPTION_KEY = "description"
LIST_TYPE_KEY = "list_type"
ORDERED_KEY = "ordered"
START_YEAR_KEY = "start_year"
END_YEAR_KEY = "end_year"
PRIVATE_KEY = "private"
SOURCES_KEY = "sources"
PREVIOUS_KEY = "previous"
NEXT_KEY = "next"
ENTRIES_KEY = "entries"

# Source keys. A list reference uses NAME_KEY, SOURCE_KIND_KEY and
# SOURCE_KEY_KEY.
SOURCE_KIND_KEY = "kind"
SOURCE_KEY_KEY = "key"
SOURCE_URL_KEY = "url"
SOURCE_REVISION_KEY = "revision"
SOURCE_CURATOR_KEY = "curator"
SOURCE_CURATOR_URL_KEY = "curator_url"

# Entry keys, beside SERIES_KEY, VOLUME_KEY, ISSUE_KEY, DATE_KEY,
# IDENTIFIERS_KEY and NOTES_KEY.
ENTRY_TYPE_KEY = "entry_type"


class SourceKind(StrEnum):
    """
    Where a list came from: the vocabulary of a source's ``kind``.

    A source with a ``key`` and no ``revision`` is a pointer: the list is
    known to exist there and was not fetched from it.
    """

    METRON_LIST = "metron-list"
    METRON_ARC = "metron-arc"
    COMICVINE_ARC = "comicvine-arc"
    # Keyed by the json-cbl file's UUID.
    JSON_CBL = "json-cbl"
    CATALOG = "catalog"
    URL = "url"
    FILE = "file"
    TAGS = "tags"


class VocabularyField(StringField):
    """
    A free string from a loose vocabulary.

    Lowercased, with runs of spaces and underscores made single hyphens,
    then known synonyms mapped to one spelling. Unknown values pass through:
    Metron, mokkari and json-cbl disagree on these vocabularies, so none of
    them can be a closed enum.
    """

    SYNONYMS: MappingProxyType[str, str] = MappingProxyType({})

    @override
    def _deserialize(self, value: Any, *args: Any, **kwargs: Any) -> str:
        value = super()._deserialize(value, *args, **kwargs)
        value = "-".join(value.lower().replace("_", " ").split())
        return self.SYNONYMS.get(value, value)


class ListTypeField(VocabularyField):
    """A list's type: event, story, characters, teams, master, creator..."""

    # Metron's plural spellings win.
    SYNONYMS = MappingProxyType({"character": "characters", "team": "teams"})


class EntryTypeField(VocabularyField):
    """An entry's role in the list: prologue, core, tie-in, epilogue..."""

    SYNONYMS = MappingProxyType({"tiein": "tie-in", "oneshot": "one-shot"})


_FULL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FullDateField(DateField):
    """
    A whole date: a date, or an ISO ``YYYY-MM-DD`` string.

    comicbox's ``DateField`` parses liberally and fills missing parts from
    today, so ``2006-07`` would become the 14th of July on the 14th of any
    month. A reading list never guesses a day.
    """

    @override
    def _deserialize(self, value: Any, *args: Any, **kwargs: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and _FULL_DATE_RE.match(text := value.strip()):
            try:
                return date.fromisoformat(text)
            except ValueError:
                pass
        reason = "Not a whole date: YYYY-MM-DD."
        raise ValidationError(reason)


class _EntryDateFieldsSchema(BaseSubSchema):
    """The comicbox date's parts, as DateSchema declares them."""

    year = IntegerField()
    month = IntegerField(minimum=1, maximum=12)
    day = IntegerField(minimum=1, maximum=31)


class EntryDateSchema(_EntryDateFieldsSchema):
    """An entry's dates: comicbox's, but whole or not at all."""

    cover_date = FullDateField(serialize_to_str=False)
    store_date = FullDateField(serialize_to_str=False)


class JsonEntryDateSchema(_EntryDateFieldsSchema):
    """An entry's dates, written as strings for JSON."""

    cover_date = FullDateField()
    store_date = FullDateField()


class SourceSchema(BaseSubSchema):
    """One place a list came from."""

    TAG_ORDER = (
        SOURCE_KIND_KEY,
        SOURCE_KEY_KEY,
        SOURCE_URL_KEY,
        SOURCE_REVISION_KEY,
        SOURCE_CURATOR_KEY,
        SOURCE_CURATOR_URL_KEY,
    )

    kind = StringField()
    key = StringField()
    url = StringField()
    revision = StringField()
    curator = StringField()
    curator_url = StringField()


class ListRefSchema(BaseSubSchema):
    """A reference to another list, such as the one before this in an order."""

    TAG_ORDER = (NAME_KEY, SOURCE_KIND_KEY, SOURCE_KEY_KEY)

    name = StringField()
    kind = StringField()
    key = StringField()


class EntrySchema(IdentifiedSchema):
    """One issue in a reading list."""

    TAG_ORDER = (
        SERIES_KEY,
        VOLUME_KEY,
        ISSUE_KEY,
        DATE_KEY,
        IDENTIFIERS_KEY,
        ENTRY_TYPE_KEY,
        NOTES_KEY,
    )

    # Declared exactly as ComicboxSubSchemaMixin declares them.
    series = SimpleNamedNestedField(schema=SeriesSchema)
    volume = SimpleNamedNestedField(
        schema=VolumeSchema,
        field=IntegerField(minimum=0),
        name_key=NUMBER_KEY,
        primitive_type=int,
    )
    issue = Nested(IssueSchema)
    date = Nested(EntryDateSchema)
    entry_type = EntryTypeField()
    notes = StringField()


class JsonEntrySchema(EntrySchema):
    """An entry with its dates serialized as strings for JSON."""

    date = Nested(JsonEntryDateSchema)


class ReadingListSubSchema(BaseSubSchema):
    """The list: a header, then its entries in reading order."""

    TAG_ORDER = (
        NAME_KEY,
        DESCRIPTION_KEY,
        LIST_TYPE_KEY,
        ORDERED_KEY,
        START_YEAR_KEY,
        END_YEAR_KEY,
        PRIVATE_KEY,
        SOURCES_KEY,
        PREVIOUS_KEY,
        NEXT_KEY,
        TAGS_KEY,
        NOTES_KEY,
        ENTRIES_KEY,
    )

    name = StringField()
    description = StringField()
    list_type = ListTypeField()
    ordered = BooleanField()
    start_year = IntegerField()
    end_year = IntegerField()
    private = BooleanField()
    # Never sorted: sorting also de-duplicates, which would lose the rank
    # order of sources, the reading order of entries and any repeated issue.
    sources = ListField(Nested(SourceSchema), sort=False)
    previous = Nested(ListRefSchema)
    next = Nested(ListRefSchema)
    tags = StringSetField()
    notes = StringField()
    entries = ListField(Nested(EntrySchema), sort=False)


class ReadingListJsonSubSchema(ReadingListSubSchema):
    """The list, with entry dates serialized as strings for JSON."""

    entries = ListField(Nested(JsonEntrySchema), sort=False)


class ReadingListYamlSchema(YamlSchema):
    """A reading list serialized as YAML. Also the in-memory model."""

    ROOT_TAG = READING_LIST_KEY
    ROOT_KEYPATH = READING_LIST_KEY

    reading_list = Nested(ReadingListSubSchema)

    class Meta(YamlSchema.Meta):
        """Schema options."""

        # Comicbox's YAML, written without aliases: reading lists refuse
        # them on read.
        render_module = YamlRenderModule


class ReadingListJsonSchema(JsonSchema):
    """A reading list serialized as JSON."""

    ROOT_TAG = READING_LIST_KEY
    ROOT_KEYPATH = READING_LIST_KEY
    TAG_ORDER = (READING_LIST_KEY, "schema")

    reading_list = Nested(ReadingListJsonSubSchema)
    schema = Constant(READING_LIST_SCHEMA_ID)
