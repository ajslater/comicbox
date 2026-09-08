"""
ListField merges the elements that dedupe to the same sort key.

`_sort_value` combined duplicates with `old_value.update(value)` and stored
the *return* of `update()`, which is always `None`. Two elements sharing a
sort key therefore collapsed into a single null: both were lost and a bare
`null` was written into the serialized list.
"""

from __future__ import annotations

from collections.abc import Mapping

from marshmallow import Schema
from marshmallow.fields import Nested

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.collection_fields import ListField
from comicbox.formats.comicbox.schema.publishing import ReprintSchema

# The comicbox schema's own reprint sort keys. `name` is deliberately absent:
# two differently worded citations of the same issue dedupe together.
_REPRINT_SORT_KEYS = (
    "language",
    "series.sort_name",
    "series.name",
    "volume.number",
    "volume.number_to",
    "issue",
)

_METRON_XML = """<MetronInfo>
  <Series><Name>Captain Science</Name></Series>
  <Reprints>
    <Reprint>Strange Academy (2020) #1</Reprint>
    <Reprint>Strange Academy #1 (2020)</Reprint>
  </Reprints>
</MetronInfo>"""


class _ReprintsSchema(Schema):
    """A stand-in for the comicbox schema's reprints field."""

    reprints = ListField(Nested(ReprintSchema), sort_keys=_REPRINT_SORT_KEYS)


def _dump(reprints: list[dict]) -> list:
    dumped = _ReprintsSchema().dump({"reprints": reprints})
    assert isinstance(dumped, Mapping)
    return dumped["reprints"]


def test_two_reprints_sharing_a_sort_key_merge() -> None:
    """The pair becomes one element, never a null."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "issue": "1", "name": "A"},
            {"series": {"name": "Strange Academy"}, "issue": "1", "name": "B"},
        ]
    )
    assert dumped == [
        {"series": {"name": "Strange Academy"}, "issue": "1", "name": "B"}
    ]


def test_merging_keeps_fields_only_the_earlier_element_had() -> None:
    """Combining is a merge, so nothing unique to either side is dropped."""
    dumped = _dump(
        [
            {
                "series": {"name": "Strange Academy"},
                "issue": "1",
                "identifiers": {"metron": {"key": "123"}},
            },
            {"series": {"name": "Strange Academy"}, "issue": "1", "name": "B"},
        ]
    )
    assert dumped == [
        {
            "series": {"name": "Strange Academy"},
            "issue": "1",
            "identifiers": {"metron": {"key": "123"}},
            "name": "B",
        }
    ]


def test_distinct_sort_keys_are_not_merged() -> None:
    """Deduplication still only fires on an actual key collision."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "issue": "2", "name": "B"},
            {"series": {"name": "Strange Academy"}, "issue": "1", "name": "A"},
        ]
    )
    assert [reprint["issue"] for reprint in dumped] == ["1", "2"]


def test_dumping_does_not_mutate_the_input() -> None:
    """Merging builds a new dict rather than updating the caller's."""
    first = {"series": {"name": "Strange Academy"}, "issue": "1", "name": "A"}
    _dump([first, {"series": {"name": "Strange Academy"}, "issue": "1", "name": "B"}])
    assert first["name"] == "A"


def test_colliding_reprints_do_not_write_a_null() -> None:
    """End to end: the comicbox dump used to emit a lone empty list item."""
    with Comicbox() as car:
        car.add_metadata(_METRON_XML, MetadataFormats.METRON_INFO)
        reprints = car.to_dict()["comicbox"]["reprints"]
        yaml = car.to_string(MetadataFormats.COMICBOX_YAML)
    assert None not in reprints
    assert all(reprint.get("name") for reprint in reprints)
    assert "- \n" not in yaml
