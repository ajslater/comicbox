"""
Reprint consolidation, and the invariants the fast path has to keep.

Consolidation used to ask DeepDiff whether two reprints conflicted, once for
every ordered pair — the dominant cost of the whole computed pass on a book
with many reprints, and quadratic in their number. It now compares flattened,
normalized fields. These tests pin the agreement rule that replaced it, and
the aliasing invariants that let the per-delta deep copy go away.
"""

from __future__ import annotations

import json
from typing import Any

from comicbox.box import Comicbox
from comicbox.box.computed import (
    _comparable,
    _parse_reprint_name,
    _reprint_fields,
    _reprints_agree,
)
from comicbox.formats import MetadataFormats
from comicbox.merge import AdditiveMerger, ReplaceMerger


def test_a_merger_never_lends_the_destination_its_source_objects() -> None:
    """
    What lets the computed pass merge a delta in without copying it first.

    Every branch of the deep merge either recurses into the destination's own
    mapping or assigns a deep copy, so a merged delta and the snapshot it went
    into never come to share a mutable object.
    """
    for merger in (AdditiveMerger, ReplaceMerger):
        source: dict[str, Any] = {
            "shared": {"list": [1, 2]},
            "top_list": [3],
            "only_source": {"a": "b"},
        }
        dest: dict[str, Any] = {"shared": {"list": [9]}, "top_list": [8]}
        merger.merge(dest, source)
        assert dest["shared"] is not source["shared"], merger
        assert dest["shared"]["list"] is not source["shared"]["list"], merger
        assert dest["top_list"] is not source["top_list"], merger
        assert dest["only_source"] is not source["only_source"], merger


def _consolidate(reprints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run a book's reprints through the computed pass and read them back."""
    metadata = json.dumps({"comicbox": {"issue": "1", "reprints": reprints}})
    with Comicbox() as car:
        car.add_metadata(metadata, MetadataFormats.COMICBOX_JSON)
        return list(car.get_computed_merged_metadata()["comicbox"]["reprints"])


def test_the_same_reprint_said_twice_becomes_one() -> None:
    """The plain case consolidation exists for."""
    reprint = {"series": {"name": "Strange Academy"}, "issue": "1"}
    assert len(_consolidate([dict(reprint), dict(reprint)])) == 1


def test_a_reprint_that_says_less_folds_into_one_that_says_more() -> None:
    """Silence is not disagreement, so the fuller reprint absorbs the sparser."""
    reprints = _consolidate(
        [
            {"series": {"name": "Strange Academy"}, "issue": "1"},
            {"series": {"name": "Strange Academy"}},
        ]
    )
    assert len(reprints) == 1
    assert reprints[0]["issue"] == "1"


def test_reprints_that_contradict_each_other_stay_apart() -> None:
    """One field they both carry and disagree on is enough to keep them two."""
    reprints = _consolidate(
        [
            {"series": {"name": "Strange Academy"}, "issue": "1"},
            {"series": {"name": "Strange Academy"}, "issue": "2"},
        ]
    )
    assert len(reprints) == 2


def test_reprints_with_nothing_in_common_stay_apart() -> None:
    """Two editions that share no field are two editions, not one said twice."""
    left = {"series": {"name": "Strange Academy"}}
    right = {"volume": {"number": 3}}
    assert not _reprints_agree(_reprint_fields(left), _reprint_fields(right))


def test_an_empty_reprint_contradicts_nothing() -> None:
    """A reprint that makes no claim cannot conflict with one that does."""
    assert _reprints_agree({}, _reprint_fields({"issue": "1"}))


def test_case_is_a_sources_habit_not_a_disagreement() -> None:
    """ignore_string_case was part of the old comparison and stays part of this one."""
    left = {"series": {"name": "Strange Academy"}, "issue": "1"}
    right = {"series": {"name": "STRANGE ACADEMY"}, "issue": "1"}
    assert _reprints_agree(_reprint_fields(left), _reprint_fields(right))


def test_representation_is_not_a_disagreement() -> None:
    """
    Both of these say volume 2.

    A volume number read out of a reprint's name is a string; the same number
    loaded through the schema is an int.
    """
    assert _comparable(2) == _comparable("2")
    left = {"name": "Doctor Strange", "volume": {"number": 2}}
    right = {"name": "Doctor Strange", "volume": {"number": "2"}}
    assert _reprints_agree(_reprint_fields(left), _reprint_fields(right))


def test_field_order_is_not_a_disagreement() -> None:
    """The old comparison ignored order; a flattened one has no order to ignore."""
    left = {"issue": "1", "series": {"name": "Strange Academy"}}
    right = {"series": {"name": "Strange Academy"}, "issue": "1"}
    assert _reprint_fields(left) == _reprint_fields(right)


def test_nested_reprint_fields_flatten_to_dotted_paths() -> None:
    """Nested mappings are compared field by field, not as whole subtrees."""
    fields = _reprint_fields({"series": {"name": "A"}, "volume": {"number": 3}})
    assert set(fields) == {"series.name", "volume.number"}


def test_a_reprint_heavy_book_consolidates_its_duplicates() -> None:
    """Thirty-two reprints, half of them repeats, end up as the distinct sixteen."""
    distinct = [
        {"name": f"Strange Academy v1 #{issue:03d} (2020) The Reprint"}
        for issue in range(1, 17)
    ]
    reprints = _consolidate([*distinct, *(dict(reprint) for reprint in distinct)])
    assert len(reprints) == len(distinct)


def test_two_reprints_sharing_a_name_do_not_share_its_parsed_values() -> None:
    """
    The name parse is memoized, so its result is shared between callers.

    Every value that reaches a reprint from it must still be that reprint's
    own: consolidation merges into these mappings in place, and one book's
    merge must not turn up in the next book that cites the same issue.
    """
    name = "Strange Academy v1 #001 (2020) The Reprint"
    reprints = _consolidate(
        [{"name": name, "issue": "1"}, {"name": name, "issue": "2"}]
    )
    assert len(reprints) == 2
    first, second = (reprint["series"] for reprint in reprints)
    assert first == second
    assert first is not second


def test_the_name_parse_is_memoized() -> None:
    """Reprint names repeat; the grammar and the glom spec do not rerun for them."""
    name = "Uncanny X-Men v3 #003 (1992) The Reprint"
    _parse_reprint_name(name)
    before = _parse_reprint_name.cache_info().hits
    _parse_reprint_name(name)
    assert _parse_reprint_name.cache_info().hits == before + 1


def test_the_computed_pass_leaves_the_merged_metadata_alone() -> None:
    """
    Consolidation merges reprints in place, so the pass works on a copy.

    Without it the box's cached merged metadata — what every source actually
    said — would come back carrying the computed pass's own conclusions.
    """
    metadata = json.dumps(
        {
            "comicbox": {
                "issue": "1",
                "reprints": [
                    {"series": {"name": "Strange Academy"}, "issue": "1"},
                    {"series": {"name": "Strange Academy"}},
                ],
            }
        }
    )
    with Comicbox() as car:
        car.add_metadata(metadata, MetadataFormats.COMICBOX_JSON)
        before = json.dumps(car.get_merged_metadata()["comicbox"]["reprints"], indent=1)
        car.to_dict()
        after = json.dumps(car.get_merged_metadata()["comicbox"]["reprints"], indent=1)
    assert before == after


def test_a_computed_delta_is_not_rewritten_by_a_later_action() -> None:
    """
    Each delta keeps saying what its own action produced.

    The deltas are what --print shows for each phase, so a later action
    rewriting an earlier one's would misreport where a value came from.
    """
    metadata = json.dumps(
        {
            "comicbox": {
                "issue": "1",
                "reprints": [
                    {"name": "Strange Academy v1 #001 (2020)"},
                    {"name": "Strange Academy v1 #001 (2020)"},
                ],
            }
        }
    )
    with Comicbox() as car:
        car.add_metadata(metadata, MetadataFormats.COMICBOX_JSON)
        deltas = {
            computed.label: json.dumps(computed.metadata, default=str, sort_keys=True)
            for computed in car.get_computed_metadata()
        }
        # Everything after "from reprint names" ran before this is read back.
        names_delta = deltas["from reprint names"]
        reprints_delta = deltas["from reprints"]
    assert json.loads(names_delta)["comicbox"]["reprints"] != []
    assert len(json.loads(names_delta)["comicbox"]["reprints"]) == 2
    assert len(json.loads(reprints_delta)["comicbox"]["reprints"]) == 1
