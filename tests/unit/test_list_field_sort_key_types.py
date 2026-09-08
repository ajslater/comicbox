"""
ListField sorts lists whose sort key slots hold mixed types.

`_sort_value` substituted `""` for a key the element didn't have, so a reprint
carrying `volume: {issue_count: 12}` and no `volume.number` put a string in the
slot where its sibling put an int. Once the pair tied on every earlier key,
`sorted()` compared the two and raised
`TypeError: '<' not supported between instances of 'int' and 'str'`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from marshmallow import Schema
from marshmallow.fields import Nested

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.base.fields.collection_fields import ListField
from comicbox.formats.comicbox.schema.publishing import ReprintSchema

# The comicbox schema's own reprint sort keys.
_REPRINT_SORT_KEYS = (
    "language",
    "series.sort_name",
    "series.name",
    "volume.number",
    "volume.number_to",
    "issue",
)

# Both reprints share a series name, so the tie falls through to volume.number,
# which only the second one has.
_COMICBOX_JSON = json.dumps(
    {
        "comicbox": {
            "issue": "1",
            "reprints": [
                {
                    "name": "Strange Academy v1 #001 (1990)",
                    "volume": {"issue_count": 12},
                },
                {"name": "Strange Academy v2 #002 (1991)"},
            ],
        }
    }
)


class _ReprintsSchema(Schema):
    """A stand-in for the comicbox schema's reprints field."""

    reprints = ListField(Nested(ReprintSchema), sort_keys=_REPRINT_SORT_KEYS)


def _dump(reprints: list[dict]) -> list:
    dumped = _ReprintsSchema().dump({"reprints": reprints})
    assert isinstance(dumped, Mapping)
    return dumped["reprints"]


def test_a_missing_key_beside_an_int_sorts() -> None:
    """The empty slot no longer compares against the int beside it."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "volume": {"number": 2}},
            {"series": {"name": "Strange Academy"}, "volume": {"issue_count": 12}},
        ]
    )
    # Absent sorts first, and neither element was lost to deduplication.
    assert [reprint["volume"] for reprint in dumped] == [
        {"issue_count": 12},
        {"number": 2},
    ]


def test_a_string_key_beside_an_int_sorts() -> None:
    """Unlike types are ranked apart rather than compared."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "volume": {"number": 2}},
            {"series": {"name": "Strange Academy"}, "issue": "1"},
        ]
    )
    assert len(dumped) == 2


def test_numbers_still_sort_numerically() -> None:
    """Ranking by type must not degrade ints into lexical strings."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "volume": {"number": n}}
            for n in (10, 2, 1)
        ]
    )
    assert [reprint["volume"]["number"] for reprint in dumped] == [1, 2, 10]


def test_an_absent_key_still_dedupes_with_an_empty_one() -> None:
    """Absent and empty share a rank, so they collide as they always did."""
    dumped = _dump(
        [
            {"series": {"name": "Strange Academy"}, "issue": "1", "name": "A"},
            {
                "series": {"name": "Strange Academy"},
                "issue": "1",
                "language": "",
                "name": "B",
            },
        ]
    )
    assert len(dumped) == 1


def test_heterogeneous_reprints_dump_end_to_end() -> None:
    """The comicbox dump used to raise straight out of `to_dict`."""
    with Comicbox() as car:
        car.add_metadata(_COMICBOX_JSON, MetadataFormats.COMICBOX_JSON)
        reprints = car.to_dict()["comicbox"]["reprints"]
    assert [reprint["name"] for reprint in reprints] == [
        "Strange Academy v1 #001 (1990)",
        "Strange Academy v2 #002 (1991)",
    ]
