"""
VerseDB API response schema.

Pass-through schema carrying a VerseDB issue-detail ``data`` object (the
server's own JSON, not the SDK's models) under the `versedb_api` root tag.
Field-level mapping happens in `comicbox/formats/versedb_api/transform.py`;
the schema here only carries the dict through unchanged.
"""

from marshmallow.fields import Raw

from comicbox.formats.base.schemas.json_schemas import JsonSchema


class VerseDBApiSchema(JsonSchema):
    """Top-level schema for VerseDB API responses."""

    ROOT_TAG: str = "versedb_api"
    ROOT_KEYPATH: str = "versedb_api"

    versedb_api = Raw()

    class Meta(JsonSchema.Meta):
        """Allow unknown to bypass through the Raw field."""

        unknown = "include"
