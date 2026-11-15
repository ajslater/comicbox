"""Comparing two reading lists: one pair per verdict."""

from typing import Any

import pytest

from comicbox.readinglists import Comparison, Verdict, compare


def _list(*numbers: int) -> dict[str, Any]:
    return {
        "name": "Civil War",
        "entries": [
            {
                "series": {"name": "Civil War", "start_year": 2006},
                "issue": {"name": str(number)},
            }
            for number in numbers
        ],
    }


_TEN = tuple(range(1, 11))


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (_TEN, _TEN, Comparison(Verdict.SAME, 1.0, (1.0, 1.0), 1.0)),
        (_TEN, (*_TEN, 11), Comparison(Verdict.SAME, 10 / 11, (1.0, 10 / 11), 1.0)),
        (
            _TEN,
            tuple(reversed(_TEN)),
            Comparison(Verdict.VARIANT, 1.0, (1.0, 1.0), 0.1),
        ),
        (_TEN, _TEN[:5], Comparison(Verdict.SUBSET, 0.5, (0.5, 1.0), 1.0)),
        (
            _TEN,
            tuple(range(21, 31)),
            Comparison(Verdict.UNRELATED, 0.0, (0.0, 0.0), 0.0),
        ),
        ((), (), Comparison(Verdict.UNRELATED, 0.0, (0.0, 0.0), 0.0)),
    ],
    ids=["same", "same-plus-one", "variant", "subset", "unrelated", "empty"],
)
def test_verdicts(a: tuple[int, ...], b: tuple[int, ...], expected: Comparison) -> None:
    assert compare(_list(*a), _list(*b)) == expected
