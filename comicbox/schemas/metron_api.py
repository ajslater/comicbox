"""
Metron API response schema.

Stub for M1 — populated in M2 with the field-by-field mapping from
mokkari's `Issue` model.
"""

from comicbox.schemas.json_schemas import JsonSchema


class MetronApiSchema(JsonSchema):
    """Stub Metron API schema. Real fields land in M2."""

    ROOT_TAG: str = "metron_api"
    ROOT_KEYPATH: str = "metron_api"
