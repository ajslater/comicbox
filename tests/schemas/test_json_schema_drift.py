"""
Drift guard: the published comicbox v2.0 JSON Schema must match the model.

The JSON Schema files in ``comicbox/schemas/v2.0/`` are hand-maintained
and serve as the production validator for the COMICBOX_JSON/YAML formats, but nothing
generates them from the Marshmallow schemas in ``comicbox/formats/comicbox/schema/``.

This test walks the Marshmallow schema tree (the source of truth) and the JSON Schema
in parallel -- following ``$ref``s, ``additionalProperties``, ``patternProperties`` and
array ``items`` -- and asserts, for every object, that:

- its set of property names matches the fields the model dumps (catches
  renamed/added/removed fields and ``$ref``s pointing at the wrong sub-schema), and
- each property's declared JSON ``type`` matches the field's type, including array
  ``items`` and scalar map values (catches e.g. an ``integer`` declared for a
  ``StringField``), and
- each enum property's declared ``enum`` values match the field's canonical enum
  members (catches added/removed/renamed enum values).
"""

import json
from inspect import isclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from marshmallow import Schema, fields
from marshmallow.fields import Nested
from marshmallow_union import Union

from comicbox.formats.comicbox.schema.json_schema import ComicboxJsonSchema
from comicbox.validate.base import SCHEMA_PATH

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import Enum

SCHEMA_DIR = SCHEMA_PATH / "v2.0"
ROOT_SCHEMA = "comicbox-v2.0.schema.json"

# Marshmallow base class -> JSON Schema ``type``. Order matters: ``Integer`` is a
# ``Number`` but maps to ``"integer"``, so it is tested first. Enum/Date/DateTime
# fields all serialize to strings in comicbox JSON.
_SCALAR_TYPES: tuple[tuple[type, str], ...] = (
    (fields.Boolean, "boolean"),
    (fields.Integer, "integer"),
    (fields.Number, "number"),
    (fields.String, "string"),
    (fields.Enum, "string"),
    (fields.Date, "string"),
    (fields.DateTime, "string"),
    (fields.List, "array"),
)


def _expected_type(field: fields.Field) -> str | None:
    """Return the JSON Schema ``type`` a field serializes to, or None to skip."""
    if isinstance(field, fields.Dict | Nested | Union):
        return "object"
    for field_type, json_type in _SCALAR_TYPES:
        if isinstance(field, field_type):
            return json_type
    return None  # Constant and anything unrecognized: don't assert a type.


def _load(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / Path(filename).name).read_text())


def _resolve(node: dict) -> dict:
    """Follow local ``$ref``s to the target schema object."""
    seen: set[str] = set()
    while "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            msg = f"Cyclic $ref detected: {ref}"
            raise AssertionError(msg)
        seen.add(ref)
        node = _load(ref)
    return node


def _item_schema(node: dict) -> dict:
    """
    Return the subschema describing a node's values.

    Object maps describe their values with ``additionalProperties`` or
    ``patternProperties``; arrays with ``items``; plain objects describe
    themselves via ``properties``.
    """
    node = _resolve(node)
    if node.get("type") == "array":
        return _resolve(node["items"])
    additional = node.get("additionalProperties")
    if isinstance(additional, dict):
        return _resolve(additional)
    if pattern := node.get("patternProperties"):
        return _resolve(next(iter(pattern.values())))
    return node


def _schema_class(field: fields.Field) -> type[Schema] | None:
    """Return the sub-schema a structured field resolves to, or None for leaves."""
    if isinstance(field, Nested):
        nested = field.nested
        return cast("type[Schema]", nested if isclass(nested) else type(nested))
    if isinstance(field, Union):
        # marshmallow_union stores its member fields here.
        for candidate in field._candidate_fields:
            if cls := _schema_class(candidate):
                return cls
        return None
    if isinstance(field, fields.Dict):
        return _schema_class(field.value_field) if field.value_field else None
    if isinstance(field, fields.List):
        return _schema_class(field.inner)
    return None


def _check_scalar_type(
    field: fields.Field, node: dict, path: str, failures: list[str]
) -> None:
    """Assert the property's declared JSON ``type`` matches the field."""
    expected = _expected_type(field)
    declared = node.get("type")
    if expected and declared and declared != expected:
        failures.append(f"{path}: model type {expected!r} != schema type {declared!r}")


def _check_enum(
    field: fields.Field, node: dict, path: str, failures: list[str]
) -> None:
    """Assert an enum property's declared values match the field's enum members."""
    if not (isinstance(field, fields.Enum) and "enum" in node):
        return
    members = cast("Iterable[Enum]", field.enum)
    model_values = {member.value for member in members}
    declared_values = set(node["enum"])
    if model_values != declared_values:
        failures.append(
            f"{path}: model enum {sorted(model_values)}"
            f" != schema enum {sorted(declared_values)}"
        )


def _check_array_items(
    field: fields.Field, node: dict, path: str, failures: list[str]
) -> None:
    """Assert an array property's ``items`` type matches the field's inner element."""
    if not isinstance(field, fields.List):
        return
    expected = _expected_type(field.inner)
    declared = _resolve(node.get("items", {})).get("type")
    if expected and declared and declared != expected:
        failures.append(
            f"{path}[]: model item type {expected!r} != schema type {declared!r}"
        )


def _check_map_values(
    field: fields.Field, node: dict, path: str, failures: list[str]
) -> None:
    """
    Assert a plain map's scalar value type matches the field's value.

    Named-dict Unions carry object values, which are verified by descent instead.
    """
    if not (isinstance(field, fields.Dict) and field.value_field is not None):
        return
    expected = _expected_type(field.value_field)
    additional = node.get("additionalProperties")
    if not (expected and expected != "object" and isinstance(additional, dict)):
        return
    declared = _resolve(additional).get("type")
    if declared and declared != expected:
        failures.append(
            f"{path}{{}}: model value type {expected!r} != schema type {declared!r}"
        )


def _check_type(
    field: fields.Field, prop: dict, path: str, failures: list[str]
) -> None:
    """Assert a property's declared JSON type matches the field, including elements."""
    node = _resolve(prop)
    _check_scalar_type(field, node, path, failures)
    _check_enum(field, node, path, failures)
    _check_array_items(field, node, path, failures)
    _check_map_values(field, node, path, failures)


def _walk(schema: Schema, node: dict, path: str, failures: list[str]) -> None:
    node = _resolve(node)
    properties = node.get("properties", {})
    model_keys = {field.data_key or name for name, field in schema.fields.items()}
    json_keys = set(properties)
    if model_keys != json_keys:
        only_model = sorted(model_keys - json_keys)
        only_json = sorted(json_keys - model_keys)
        failures.append(f"{path}: model-only={only_model} schema-only={only_json}")
    for name, field in schema.fields.items():
        key = field.data_key or name
        if key not in properties:
            continue
        _check_type(field, properties[key], f"{path}.{key}", failures)
        if sub_cls := _schema_class(field):
            _walk(sub_cls(), _item_schema(properties[key]), f"{path}.{key}", failures)


def test_json_schema_matches_model() -> None:
    """Every object in the v2.0 JSON Schema must match its Marshmallow fields."""
    failures: list[str] = []
    _walk(ComicboxJsonSchema(), _load(ROOT_SCHEMA), "<root>", failures)
    assert not failures, "v2.0 JSON Schema drifted from the model:\n" + "\n".join(
        failures
    )
