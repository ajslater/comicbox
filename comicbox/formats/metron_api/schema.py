"""
Metron API response schema.

A pass-through schema that accepts the mokkari `Issue.model_dump(mode="json")`
dict under the `metron_api` root tag. The transform layer
(`comicbox/transforms/metron_api/`) maps fields into the comicbox
internal schema; the schema's job here is just to wrap-and-pass.
"""

from marshmallow.fields import Raw

from comicbox.formats.base.schemas.json_schemas import JsonSchema, JsonSubSchema


class MetronApiSubSchema(JsonSubSchema):
    """Pass-through holder for mokkari issue dicts."""

    class Meta(JsonSubSchema.Meta):
        """Accept any field the upstream library returns."""

        # We don't enumerate every mokkari field; the transform consumes
        # whatever's present.
        unknown = "include"


class MetronApiSchema(JsonSchema):
    """Top-level schema for Metron API responses."""

    ROOT_TAG: str = "metron_api"
    ROOT_KEYPATH: str = "metron_api"

    metron_api = Raw()

    class Meta(JsonSchema.Meta):
        """Allow unknown to bypass through the Raw field."""

        unknown = "include"
