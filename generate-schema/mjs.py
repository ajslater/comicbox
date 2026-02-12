#!/usr/bin/env python
"""Create jsonschema from marshmallow definition."""

from enum import Enum
from pathlib import Path

from marshmallow import fields
from marshmallow_jsonschema import JSONSchema, base

from comicbox.fields.enum_fields import EnumField
from comicbox.schemas.comicbox.json_schema import ComicboxJsonSchema

schema = ComicboxJsonSchema()

# Monkey Patch marshmallow-jsonchema
base.PY_TO_JSON_TYPES_MAP[fields._ContantT] = {"type": "const"}  # noqa: SLF001, # pyright: ignore[reportArgumentType]
base.MARSHMALLOW_TO_PY_TYPES_PAIRS.extend(
    [  # pyright: ignore[reportArgumentType]
        ((fields.Constant, fields._ContantT)),  # noqa: SLF001
        ((EnumField, Enum)),
    ]
)


json_schema = JSONSchema()
Path("generated.schema.json").write_text(json_schema.dumps(schema))
