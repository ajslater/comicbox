"""
The scope channel resolves by compile phase, not by argument order.

A metaspec with `assign_global` publishes its result into glom's per call
globals and others read it back as `S.globals.comicbox.<key>`. glom evaluates
the compiled dict in key insertion order, so a reader compiled ahead of the
producer read nothing and fell through to its own default -- no error, no log,
just the wrong id source on every tag in the file. The whole contract was one
comment reading "must come before most other resources". Now the compiler
plants producers in phase one and everything else in phase two, and refuses a
channel that could not resolve at all.
"""

from __future__ import annotations

from typing import Any

import pytest
from glom import glom

from comicbox.formats.base.transforms.spec import (
    GLOBAL_SCOPE_PREFIX,
    MetaSpec,
    create_specs_to_comicbox,
)

SCOPE_PID = f"{GLOBAL_SCOPE_PREFIX}.pid"
FALLBACK = "THE-FALLBACK"


def _publish(values: dict[str, Any]) -> dict[str, Any] | None:
    """Publish the id source the file named, the way metron's producer does."""
    if id_source := values.get("id"):
        return {"pid": id_source}
    return None


def _read(values: dict[str, Any]) -> str:
    """Read the published id source, or fall back the way ~15 call sites do."""
    return values.get(SCOPE_PID, FALLBACK)


def _producer(**kwargs: Any) -> MetaSpec:
    return MetaSpec(
        key_map={"pid": ("id",)}, spec=_publish, assign_global=True, **kwargs
    )


def _reader() -> MetaSpec:
    return MetaSpec(key_map={"out": ("name", SCOPE_PID)}, spec=_read)


def _compile(*metaspecs: MetaSpec):
    return create_specs_to_comicbox(*metaspecs, comicbox_root_keypath="")


def test_reader_declared_before_producer_still_reads() -> None:
    """The regression test for the deleted ordering comment."""
    specs = _compile(_reader(), _producer())
    assert glom({"id": "metron", "name": "Bat"}, dict(specs))["out"] == "metron"


def test_producer_declared_first_reads_the_same() -> None:
    specs = _compile(_producer(), _reader())
    assert glom({"id": "metron", "name": "Bat"}, dict(specs))["out"] == "metron"


def test_runtime_missing_value_still_falls_back() -> None:
    """Compile time strictness must not tighten runtime. A file may name none."""
    specs = _compile(_reader(), _producer())
    assert glom({"name": "Bat"}, dict(specs))["out"] == FALLBACK


def test_scope_read_without_a_producer_raises() -> None:
    with pytest.raises(RuntimeError, match="no metaspec in this compile publishes"):
        _compile(_reader())


def test_two_producing_metaspecs_raise() -> None:
    """A second publish replaces the whole scope mapping."""
    with pytest.raises(RuntimeError, match="only one destination may publish"):
        _compile(
            _producer(),
            MetaSpec(key_map={"other": ("id",)}, spec=_publish, assign_global=True),
            _reader(),
        )


def test_one_producer_with_two_destinations_raises() -> None:
    with pytest.raises(RuntimeError, match="only one destination may publish"):
        _compile(
            MetaSpec(
                key_map={"pid": ("id",), "other": ("id",)},
                spec=_publish,
                assign_global=True,
            ),
            _reader(),
        )


def test_producer_reading_the_scope_raises() -> None:
    """Its own read is evaluated before its publish."""
    with pytest.raises(RuntimeError, match="also reads"):
        _compile(
            MetaSpec(
                key_map={"pid": ("id", SCOPE_PID)}, spec=_publish, assign_global=True
            )
        )


def test_dotted_producer_destination_raises() -> None:
    """`T['a.b']` is one literal key. A reader descends `['a']['b']`."""
    with pytest.raises(RuntimeError, match="dotted destination"):
        _compile(
            MetaSpec(key_map={"a.pid": ("id",)}, spec=_publish, assign_global=True)
        )


def test_lone_string_scope_source_raises() -> None:
    """Alone it compiles to a data path under the source root and never matches."""
    with pytest.raises(RuntimeError, match="as its only source"):
        _compile(_producer(), MetaSpec(key_map={"out": SCOPE_PID}, spec=_read))


def test_a_producer_no_one_reads_is_allowed() -> None:
    assert glom({"id": "metron"}, dict(_compile(_producer())))["pid"] == "metron"
