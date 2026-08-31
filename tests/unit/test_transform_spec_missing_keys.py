"""
Missing sources must be absent from the multi-source `values` dict.

`MetaSpec` key maps whose source is a tuple hand the spec function a dict of
every named source. A source the file didn't supply used to arrive as an
explicit ``None``, which silently disabled every ``values.get(key, default)``
written against that dict -- ``dict.get`` substitutes its default only when the
key is *absent*, never when it is present and None.
"""

from __future__ import annotations

from typing import Any

from glom import glom

from comicbox.formats.base.transforms.spec import MetaSpec, create_specs_to_comicbox

SENTINEL = "THE-DEFAULT"


def _run(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Run a two-source MetaSpec and hand back the values dict it produced."""
    captured: dict[str, Any] = {}

    def spec(values: dict[str, Any]) -> dict:
        captured.update(values)
        return {}

    specs = create_specs_to_comicbox(
        MetaSpec(key_map={"dest": keys}, spec=spec),
        comicbox_root_keypath="",
    )
    glom(source, dict(specs))
    return captured


def test_missing_source_key_is_absent_not_none() -> None:
    values = _run({"present": "yes"}, ("present", "missing"))
    assert values["present"] == "yes"
    assert "missing" not in values


def test_get_with_default_returns_the_default() -> None:
    """The property the ~17 metron primary-id-source call sites rely on."""
    values = _run({"present": "yes"}, ("present", "missing"))
    assert values.get("missing", SENTINEL) == SENTINEL


def test_empty_source_value_is_also_absent() -> None:
    """`skip=is_empty` treats an empty value as unsupplied."""
    values = _run({"present": "yes", "blank": ""}, ("present", "blank"))
    assert values.get("blank", SENTINEL) == SENTINEL


def test_zero_is_a_real_value_and_survives() -> None:
    """`is_empty` respects zero, so 0 must not be mistaken for missing."""
    values = _run({"zero": 0}, ("zero", "missing"))
    assert values.get("zero", SENTINEL) == 0


def test_all_sources_missing_yields_an_empty_dict() -> None:
    values = _run({"unrelated": 1}, ("nope", "also-nope"))
    assert values == {}
