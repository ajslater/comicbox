"""Comparing two reading lists: one pair per verdict, and each threshold."""

from typing import Any

import pytest

from comicbox.readinglists import Comparison, Verdict, compare
from comicbox.readinglists.compare import CONTAINS, ORDER_AGREEMENT


def _list(*numbers: int, **header: Any) -> dict[str, Any]:
    return {
        "name": "Civil War",
        "entries": [
            {
                "series": {"name": "Civil War", "start_year": 2006},
                "issue": {"name": str(number)},
            }
            for number in numbers
        ],
        **header,
    }


_TEN = tuple(range(1, 11))
_HUNDRED = tuple(range(1, 101))


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


def _sharing(shared: int) -> tuple[int, ...]:
    """Hold ``shared`` of the hundred, and as many others."""
    return (*_HUNDRED[:shared], *range(1001, 1001 + 100 - shared))


@pytest.mark.parametrize(
    ("b", "verdict"),
    [
        (_sharing(75), Verdict.SAME),
        (_sharing(74), Verdict.UNRELATED),
        (_HUNDRED[:75], Verdict.SAME),
        (_HUNDRED[:74], Verdict.SUBSET),
        # (0.74, 0.79): one threshold for both sides makes this a subset.
        ((*_HUNDRED[:74], *range(1001, 1021)), Verdict.SUBSET),
    ],
    ids=["both-at", "both-under", "one-at", "one-under", "one-at-0.79"],
)
def test_the_containment_threshold(b: tuple[int, ...], verdict: Verdict) -> None:
    assert CONTAINS == 0.75
    assert compare(_list(*_HUNDRED), _list(*b)).verdict is verdict


@pytest.mark.parametrize(
    ("moved", "verdict"), [(10, Verdict.SAME), (11, Verdict.VARIANT)]
)
def test_the_order_threshold(moved: int, verdict: Verdict) -> None:
    """Moving the first ``moved`` to the end leaves 100 - moved in order."""
    assert ORDER_AGREEMENT == 0.9
    b = (*_HUNDRED[moved:], *_HUNDRED[:moved])
    comparison = compare(_list(*_HUNDRED), _list(*b))
    assert comparison.order_agreement == (100 - moved) / 100
    assert comparison.verdict is verdict


def test_an_unordered_list_has_no_order_to_agree_with() -> None:
    tags = _list(*reversed(_TEN), ordered=False)
    comparison = compare(_list(*_TEN), tags)
    assert comparison == Comparison(Verdict.SAME, 1.0, (1.0, 1.0), None)
    assert compare(tags, _list(*_TEN[:5])).verdict is Verdict.SUBSET
