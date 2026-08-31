"""
Suppressed schema errors are logged instead of vanishing.

`ClearingErrorStore` exists so one malformed tag can't condemn a whole file,
but it accumulated the cleaned errors into `clear_errors` and nothing ever
read that attribute. Bad metadata was therefore indistinguishable from absent
metadata. It now names every field it drops, and what was in it.

`_invoke_schema_validators` is covered here too: it swallowed the `data`
keyword instead of forwarding it, so the first `@validates_schema` hook added
to any comicbox schema would have raised TypeError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from loguru import logger
from marshmallow import ValidationError, validates_schema

from comicbox.formats.base.fields.fields import StringField
from comicbox.formats.base.fields.number_fields import IntegerField
from comicbox.formats.base.schemas.base import BaseSubSchema

if TYPE_CHECKING:
    from collections.abc import Iterator


class _TagSchema(BaseSubSchema):
    """A one-tag schema for exercising the store directly."""

    tag = StringField()
    count = IntegerField()


class _ValidatedSchema(BaseSubSchema):
    """A schema with the kind of hook the missing kwarg would have broken."""

    tag = StringField()

    @validates_schema
    def check_tag(self, data: dict, **_kwargs: object) -> None:
        """Reject one sentinel value."""
        if data.get("tag") == "bad":
            reason = "tag is bad"
            raise ValidationError(reason, "tag")


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """Capture WARNING records and restore the path prefix afterward."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        logger.remove(handler_id)
        _TagSchema().set_path(None)


def test_a_dropped_field_is_named(warnings: list[str]) -> None:
    """The warning says which field went away and why."""
    assert _TagSchema().load({"tag": {"nested": "dict"}}) == {}
    assert len(warnings) == 1
    message = warnings[0]
    assert "tag" in message
    assert "is not a string" in message


def test_a_dropped_field_reports_its_value(warnings: list[str]) -> None:
    """The offending value is in the warning, so the tag is findable."""
    _TagSchema().load({"tag": {"nested": "dict"}})
    assert "nested" in warnings[0]


def test_the_warning_is_prefixed_with_the_path(warnings: list[str]) -> None:
    """A batch run has to be able to tell which file complained."""
    _TagSchema(path="captain-science-001.cbz").load({"tag": ["a", "list"]})
    assert warnings[0].startswith("captain-science-001.cbz: ")


def test_good_data_logs_nothing(warnings: list[str]) -> None:
    """No false positives on metadata that parses."""
    assert _TagSchema().load({"tag": "Marvel", "count": "12"}) == {
        "tag": "Marvel",
        "count": 12,
    }
    assert warnings == []


def test_ignored_errors_stay_quiet(warnings: list[str]) -> None:
    """
    An explicit null is a normal absence, not a defect.

    "Field may not be null." is in the ignore set, and ignored messages must
    not become log noise now that the rest are visible.
    """
    assert _TagSchema().load({"tag": None}) == {}
    assert warnings == []


def test_unparseable_numbers_are_reported(warnings: list[str]) -> None:
    """Junk in a number tag is a real drop and says so."""
    assert _TagSchema().load({"count": "not a number"}) == {}
    assert len(warnings) == 1
    assert "count" in warnings[0]


def test_schema_validators_run(warnings: list[str]) -> None:
    """
    A `@validates_schema` hook loads without raising TypeError.

    `_invoke_schema_validators` used to drop `data` on the floor, so
    marshmallow's own signature check failed before any hook body ran.
    """
    assert _ValidatedSchema().load({"tag": "fine"}) == {"tag": "fine"}
    assert warnings == []


def test_schema_validator_failures_are_logged(warnings: list[str]) -> None:
    """A hook that rejects data gets its message surfaced, not swallowed."""
    _ValidatedSchema().load({"tag": "bad"})
    assert len(warnings) == 1
    assert "tag is bad" in warnings[0]
