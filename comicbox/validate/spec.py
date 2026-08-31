"""
Deferred validator declarations.

Format registrations name their schema validator with a ``ValidatorSpec``
instead of constructing one. Construction is not cheap: it imports
``xmlschema`` or ``jsonschema`` and then compiles an XSD 1.1 or JSON
Schema document. Doing that eagerly put ~200ms of schema compilation into
every ``import comicbox.formats`` — paid by every read, write, and CLI
run — while the only consumer is the opt-in ``--validate`` path in
``comicbox.box.validate``.

Naming a validator here is pure data. Nothing heavier than ``comicbox``
itself is imported until ``build_validator()`` is called.
"""

from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comicbox.validate.base import BaseValidator


class ValidatorType(Enum):
    """Schema languages comicbox validates metadata against."""

    XML = "xml"
    JSON = "json"
    YAML = "yaml"


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    """
    A schema language and the schema file to validate against.

    Frozen and hashable so ``build_validator()`` can memoize on it: the
    three comicbox-native registrations name the same schema file, and
    without the memo every ``validate_source()`` call would recompile.
    """

    validator_type: ValidatorType
    schema_path: str


@cache
def build_validator(spec: ValidatorSpec) -> "BaseValidator":
    """Construct (and compile) the validator a spec names."""
    # Lazy imports: reaching this function is what makes the xmlschema /
    # jsonschema dependency chain worth loading. See the module docstring.
    if spec.validator_type is ValidatorType.XML:
        from comicbox.validate.xml_validator import XmlValidator

        return XmlValidator(spec.schema_path)
    if spec.validator_type is ValidatorType.JSON:
        from comicbox.validate.json_validator import JsonValidator

        return JsonValidator(spec.schema_path)
    if spec.validator_type is ValidatorType.YAML:
        from comicbox.validate.yaml_validator import YamlValidator

        return YamlValidator(spec.schema_path)
    # Spelled out rather than falling through to a default: a new
    # ValidatorType silently building the wrong validator would look like
    # a schema bug, not a missing branch.
    reason = f"No validator for {spec.validator_type}"
    raise NotImplementedError(reason)


@cache
def validation_failure_exceptions() -> tuple[type[Exception], ...]:
    """
    Get the exceptions a validator raises for invalid data.

    Deferred for the same reason the validators are: importing these
    names at module scope pulls in all of ``xmlschema`` and
    ``jsonschema`` even when nothing validates.
    """
    from jsonschema.exceptions import (
        FormatError,
        SchemaError,
        UndefinedTypeCheck,
        UnknownType,
        ValidationError,
    )
    from xmlschema.exceptions import XMLSchemaException

    return (
        XMLSchemaException,
        # JsonValidation Errors
        ValidationError,
        SchemaError,
        UndefinedTypeCheck,
        UnknownType,
        FormatError,
    )
