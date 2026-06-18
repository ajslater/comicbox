"""
ComicVine API response schema.

Pass-through schema mirroring the simyan `Issue.model_dump(mode="json")`
shape under the `comicvine_api` root tag. Field-level mapping happens
in `comicbox/formats/comicvine_api/transform.py`; the schema here only carries
the dict through unchanged.
"""

from marshmallow.fields import Raw

from comicbox.formats.base.schemas.json_schemas import JsonSchema


class ComicVineApiSchema(JsonSchema):
    """Top-level schema for ComicVine API responses."""

    ROOT_TAG: str = "comicvine_api"
    ROOT_KEYPATH: str = "comicvine_api"

    comicvine_api = Raw()

    class Meta(JsonSchema.Meta):
        """Allow unknown to bypass through the Raw field."""

        unknown = "include"
