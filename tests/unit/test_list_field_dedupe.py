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
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema

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


def _dump_comicbox(reprints: list[dict]) -> list:
    dumped = ComicboxYamlSchema().dump({"comicbox": {"reprints": reprints}})
    assert isinstance(dumped, Mapping)
    return dumped["comicbox"]["reprints"]


def test_name_only_reprints_stay_distinct() -> None:
    """Reprints with no parsed series, volume or issue keep their own names."""
    dumped = _dump_comicbox(
        [
            {"name": "A", "identifiers": {"metron": {"key": "1"}}},
            {"name": "B", "identifiers": {"metron": {"key": "2"}}},
        ]
    )
    assert dumped == [
        {"name": "A", "identifiers": {"metron": {"key": "1"}}},
        {"name": "B", "identifiers": {"metron": {"key": "2"}}},
    ]


def test_name_only_reprints_with_one_name_still_merge() -> None:
    """Two sources citing the same unparsed name are one reprint."""
    dumped = _dump_comicbox(
        [
            {"name": "A", "identifiers": {"metron": {"key": "1"}}},
            {"name": "A"},
        ]
    )
    assert dumped == [{"name": "A", "identifiers": {"metron": {"key": "1"}}}]


def test_comicbox_schema_keeps_name_only_reprints() -> None:
    """The comicbox YAML schema dump keeps a facsimile apart from its original."""
    dumped = _dump_comicbox([{"name": "X #1"}, {"name": "X #1 Facsimile"}])
    names = [reprint["name"] for reprint in dumped]
    assert names == ["X #1", "X #1 Facsimile"]


def test_unparsed_metron_reprints_survive_to_dict() -> None:
    """End to end: MetronInfo reprints that parse to nothing all survive."""
    xml = """<MetronInfo>
  <Series><Name>S</Name></Series>
  <Reprints>
    <Reprint id="11">#1</Reprint>
    <Reprint>(2019)</Reprint>
    <Reprint>(2020)</Reprint>
  </Reprints>
</MetronInfo>"""
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        reprints = car.to_dict()["comicbox"]["reprints"]
    assert sorted(reprint["name"] for reprint in reprints) == [
        "#1",
        "(2019)",
        "(2020)",
    ]


def _reprint(issue: str, name: str, **ids: str) -> dict:
    reprint: dict = {"series": {"name": "X"}, "issue": issue, "name": name}
    if ids:
        reprint["identifiers"] = {source: {"key": key} for source, key in ids.items()}
    return reprint


def _ids(reprint: Mapping) -> dict:
    return {
        source: identifier["key"]
        for source, identifier in reprint.get("identifiers", {}).items()
    }


def test_reprints_with_differing_ids_stay_apart() -> None:
    """Two ids from one database name two reprints, whatever they parse to."""
    dumped = _dump_comicbox(
        [_reprint("1", "X #1", metron="11"), _reprint("1", "X #1 F", metron="22")]
    )
    assert [_ids(reprint) for reprint in dumped] == [
        {"metron": "11"},
        {"metron": "22"},
    ]
    assert [reprint["name"] for reprint in dumped] == ["X #1", "X #1 F"]


def test_reprints_with_equal_ids_merge() -> None:
    """The same id is the same reprint, as before."""
    dumped = _dump_comicbox(
        [_reprint("1", "X #1", metron="11"), _reprint("1", "X #1 F", metron="11")]
    )
    assert len(dumped) == 1
    assert _ids(dumped[0]) == {"metron": "11"}


def test_an_id_beside_no_id_merges() -> None:
    """Nothing says a reprint without an id differs, so it merges."""
    dumped = _dump_comicbox([_reprint("1", "X #1", metron="11"), _reprint("1", "B")])
    assert len(dumped) == 1
    assert _ids(dumped[0]) == {"metron": "11"}
    assert dumped[0]["name"] == "B"


def test_ids_from_two_databases_do_not_conflict() -> None:
    """A Metron id and a Comic Vine id merge, and both are kept."""
    dumped = _dump_comicbox(
        [_reprint("1", "A", metron="11"), _reprint("1", "B", comicvine="5")]
    )
    assert len(dumped) == 1
    assert _ids(dumped[0]) == {"metron": "11", "comicvine": "5"}


def test_three_reprints_two_sharing_an_id() -> None:
    """The two that share an id merge; the third stays apart."""
    dumped = _dump_comicbox(
        [
            _reprint("1", "A", metron="11"),
            _reprint("1", "B", metron="22"),
            _reprint("1", "C", metron="11"),
            _reprint("1", "D"),
        ]
    )
    # The id-less reprint joins the first one it doesn't contradict.
    assert [(reprint["name"], _ids(reprint)) for reprint in dumped] == [
        ("D", {"metron": "11"}),
        ("B", {"metron": "22"}),
    ]


def test_alternative_names_with_differing_ids_stay_apart() -> None:
    """The other identified ListField follows the same rule."""
    md = {
        "comicbox": {
            "series": {
                "name": "S",
                "alternative_names": [
                    {"name": "Alt", "identifiers": {"metron": {"key": "1"}}},
                    {"name": "Alt", "identifiers": {"metron": {"key": "2"}}},
                ],
            }
        }
    }
    dumped = ComicboxYamlSchema().dump(md)
    assert isinstance(dumped, Mapping)
    alt_names = dumped["comicbox"]["series"]["alternative_names"]
    assert [_ids(alt_name) for alt_name in alt_names] == [
        {"metron": "1"},
        {"metron": "2"},
    ]


def test_metron_reprints_with_differing_ids_survive_end_to_end() -> None:
    """MetronInfo in, to_dict and MetronInfo out all keep ids 11 and 22."""
    xml = """<MetronInfo>
  <Series><Name>S</Name></Series>
  <Reprints>
    <Reprint id="11">X #1</Reprint>
    <Reprint id="22">X #1 Facsimile</Reprint>
  </Reprints>
</MetronInfo>"""
    with Comicbox() as car:
        car.add_metadata(xml, MetadataFormats.METRON_INFO)
        reprints = car.to_dict()["comicbox"]["reprints"]
        written = car.to_string(MetadataFormats.METRON_INFO)
    assert sorted(_ids(reprint)["metron"] for reprint in reprints) == ["11", "22"]
    assert '<Reprint id="11">X #1</Reprint>' in written
    assert '<Reprint id="22">X #1 Facsimile</Reprint>' in written
