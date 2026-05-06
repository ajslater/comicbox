"""
ComicVine API response schema.

Stub for M1 — populated in M6 with the field-by-field mapping from
simyan's `Issue` model.
"""

from comicbox.schemas.json_schemas import JsonSchema


class ComicVineApiSchema(JsonSchema):
    """Stub ComicVine API schema. Real fields land in M6."""

    ROOT_TAG: str = "comicvine_api"
    ROOT_KEYPATH: str = "comicvine_api"
