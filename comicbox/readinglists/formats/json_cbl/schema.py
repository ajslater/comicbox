"""
json-cbl 1.0, comicbox's own description of it.

The spec is ``schema/1.0/comic-reading-list.schema.json`` in
github.com/ComicReadingLists/json-cbl-standard, vendored as
``comicbox/schemas/json-cbl-v1.0.schema.json`` for validation only. These
schemas are what read and write.
"""

import sys
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from marshmallow.fields import Nested

from comicbox.formats.base.fields.collection_fields import ListField
from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import DecimalField, IntegerField
from comicbox.formats.base.fields.time_fields import DateField
from comicbox.formats.base.schemas.json_schemas import JsonSchema, JsonSubSchema

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

FILE_DETAILS_KEY = "fileDetails"
LIST_DETAILS_KEY = "listDetails"
NOTES_KEY = "notes"
ISSUE_LIST_KEY = "issueList"
VERSION_KEY = "version"
UUID_KEY = "UUID"
NAME_KEY = "name"
DESCRIPTION_KEY = "description"
PUBLISHER_KEY = "publisher"
IMPRINT_KEY = "imprint"
START_YEAR_KEY = "startYear"
END_YEAR_KEY = "endYear"
TYPE_KEY = "type"
TAGS_KEY = "tags"
COVER_IMAGE_URLS_KEY = "coverImageURLs"
RELATIONSHIPS_KEY = "relationships"
RELATIONSHIP_KEY = "relationship"
SOURCE_KEY = "source"
URL_KEY = "url"
ID_KEY = "id"
SERIES_NAME_KEY = "seriesName"
SERIES_START_YEAR_KEY = "seriesStartYear"
ISSUE_NUMBER_KEY = "issueNumber"
ISSUE_COVER_DATE_KEY = "issueCoverDate"
ISSUE_TYPE_KEY = "issueType"
SERIES_KEY = "series"
ISSUE_KEY = "issue"


def _with_required(
    tag_order: tuple[str, ...], required: Mapping[str, Any], data: dict
) -> dict:
    """Add each missing required key's empty value, in tag order."""
    if not (missing := {key: v for key, v in required.items() if key not in data}):
        return data
    values = {**missing, **data}
    return {key: values[key] for key in tag_order if key in values}


class JsonCblSubSchema(JsonSubSchema):
    """A json-cbl object, written with its required keys even when empty."""

    REQUIRED: MappingProxyType[str, Any] = MappingProxyType({})

    @override
    @classmethod
    def sort_dump(cls, data: dict) -> dict:
        """Sort, then restore the required keys."""
        return _with_required(cls.TAG_ORDER, cls.REQUIRED, super().sort_dump(data))


class JsonCblFileDetailsSchema(JsonCblSubSchema):
    """The format version and the file's UUID."""

    TAG_ORDER = (VERSION_KEY, UUID_KEY)

    version = DecimalField()
    UUID = StringField()


class JsonCblRelationshipSchema(JsonCblSubSchema):
    """A list before or after this one."""

    TAG_ORDER = (NAME_KEY, UUID_KEY, RELATIONSHIP_KEY)
    REQUIRED = MappingProxyType({NAME_KEY: ""})

    name = StringField()
    UUID = StringField()
    relationship = StringField()


class JsonCblSourceSchema(JsonCblSubSchema):
    """A website with information about the list."""

    TAG_ORDER = (NAME_KEY, URL_KEY, ID_KEY)

    name = StringField()
    url = StringField()
    id = StringField()


class JsonCblListDetailsSchema(JsonCblSubSchema):
    """The list's header."""

    TAG_ORDER = (
        NAME_KEY,
        DESCRIPTION_KEY,
        PUBLISHER_KEY,
        IMPRINT_KEY,
        START_YEAR_KEY,
        END_YEAR_KEY,
        TYPE_KEY,
        TAGS_KEY,
        COVER_IMAGE_URLS_KEY,
        RELATIONSHIPS_KEY,
        SOURCE_KEY,
    )
    REQUIRED = MappingProxyType({NAME_KEY: ""})

    name = StringField()
    description = StringField()
    publisher = StringField()
    imprint = StringField()
    startYear = IntegerField()  # noqa: N815
    endYear = IntegerField()  # noqa: N815
    type = StringField()
    tags = ListField(StringField(), sort=False)
    coverImageURLs = ListField(StringField(), sort=False)  # noqa: N815
    relationships = ListField(Nested(JsonCblRelationshipSchema), sort=False)
    source = ListField(Nested(JsonCblSourceSchema), sort=False)


class JsonCblIdSchema(JsonCblSubSchema):
    """One database's series and issue ids."""

    TAG_ORDER = (NAME_KEY, SERIES_KEY, ISSUE_KEY)

    name = StringField()
    series = StringField()
    issue = StringField()


class JsonCblIssueSchema(JsonCblSubSchema):
    """One issue in reading order."""

    TAG_ORDER = (
        SERIES_NAME_KEY,
        SERIES_START_YEAR_KEY,
        ISSUE_NUMBER_KEY,
        ISSUE_COVER_DATE_KEY,
        ISSUE_TYPE_KEY,
        ID_KEY,
    )

    seriesName = StringField()  # noqa: N815
    seriesStartYear = IntegerField()  # noqa: N815
    issueNumber = StringField()  # noqa: N815
    issueCoverDate = DateField()  # noqa: N815
    issueType = StringField()  # noqa: N815
    id = ListField(Nested(JsonCblIdSchema), sort=False)


class JsonCblSchema(JsonSchema):
    """
    A json-cbl document.

    json-cbl has no root key. ``fileDetails``, which it requires, stands in
    for one, so a document without it is not taken for json-cbl.
    """

    ROOT_TAG = FILE_DETAILS_KEY
    ROOT_KEYPATH = FILE_DETAILS_KEY
    TAG_ORDER = (FILE_DETAILS_KEY, LIST_DETAILS_KEY, NOTES_KEY, ISSUE_LIST_KEY)
    REQUIRED = MappingProxyType({ISSUE_LIST_KEY: ()})

    fileDetails = Nested(JsonCblFileDetailsSchema)  # noqa: N815
    listDetails = Nested(JsonCblListDetailsSchema)  # noqa: N815
    notes = StringField()
    issueList = ListField(Nested(JsonCblIssueSchema), sort=False)  # noqa: N815

    @override
    @classmethod
    def sort_dump(cls, data: dict) -> dict:
        """Sort, then restore the required keys."""
        return _with_required(cls.TAG_ORDER, cls.REQUIRED, super().sort_dump(data))
