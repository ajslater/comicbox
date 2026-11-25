"""Compare two lists: the same list, or a different one."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rapidfuzz.distance import LCSseq

from comicbox.readinglists.combine.fields import is_ordered
from comicbox.readinglists.combine.groups import group_rows
from comicbox.readinglists.schema import ENTRIES_KEY
from comicbox.readinglists.serialize import load_model

# Calibrated on 2026-11-14 against DieselTech CBL lists (fetched to a scratch
# directory, never into the repo), matched by ComicVine id and by name, and
# measured again after R1-G with the same results. contains is (a in b,
# b in a); order is order_agreement; the verdict is what these thresholds
# give.
#
#   Crimson Tide     CBRO 132 vs LoCG 116      (0.83, 0.95)  0.45  variant
#   House of Q    CBRO 64 vs LoCG 51        (0.77, 0.96)  0.37  variant
#   Crimson Tide     CBRO 132 vs Official 98   (0.71, 0.96)  0.49  subset
#   Crimson Tide     LoCG 116 vs Official 98   (0.84, 0.99)  0.98  same
#   Infinity G.   CBRO 51 vs LoCG 58        (0.92, 0.81)  1.00  same
#   Sealed Wars   CBRO 230 vs LoCG 229      (1.00, 1.00)  1.00  same
#   Crimson Tide II  CBRO 153 vs LoCG 152      (0.99, 1.00)  1.00  same
#   Sealed Wars   CBRO 230 vs CBH 60        (0.17, 0.67)  0.47  unrelated
#   different events                        (0.00, 0.00)        unrelated
#   a list against its first half          (0.50, 1.00)  1.00  subset
#
# Two curators' takes on one event held 0.77 or more of each other, so a
# list that holds 0.75 of the other counts; the 0.9 the plan started from
# called those subsets. Official's list sits almost wholly inside CBRO's,
# which holds only 0.71 of it, so that pair is a subset. CBH's simplified
# list shares 0.67 at most and stays unrelated. One threshold serves both
# sides: no measured pair holds between 0.75 and 0.8. Orders that agree
# measured 0.98 or more and orders that do not 0.49 or less, so 0.9
# separates them. DieselTech has no CMRO lists to measure.

# How much of a list the other must hold to count: both ways for the same
# list or a variant, one way for a subset.
CONTAINS = 0.75
# The share of shared entries the two orders must agree on to be the same.
ORDER_AGREEMENT = 0.9


class Verdict(StrEnum):
    """What two lists are to each other, decided in this order."""

    # Each contains the other and the orders agree. Safe to combine.
    SAME = "same"
    # Each contains the other, in different orders: two takes on one event.
    VARIANT = "variant"
    # One contains the other, as tags do a curated list.
    SUBSET = "subset"
    UNRELATED = "unrelated"


@dataclass(frozen=True, slots=True)
class Comparison:
    """
    How two lists compare.

    ``overlap`` is the shared issues over all issues. ``contains`` is the
    share of ``a`` found in ``b``, then of ``b`` found in ``a``.
    ``order_agreement`` is the longest common subsequence of the shared
    issues over their count, or None when either list is marked unordered,
    since such a list has no order to agree with.
    """

    verdict: Verdict
    overlap: float
    contains: tuple[float, float]
    order_agreement: float | None


def _share(part: set[int], whole: set[int]) -> float:
    return len(part & whole) / len(whole) if whole else 0.0


def _order_agreement(sequences: Sequence[Sequence[int]], shared: set[int]) -> float:
    if not shared:
        return 0.0
    a, b = ([group for group in sequence if group in shared] for sequence in sequences)
    return LCSseq.similarity(a, b) / len(shared)


def _verdict(contains: tuple[float, float], order_agreement: float | None) -> Verdict:
    if min(contains) >= CONTAINS:
        if order_agreement is None or order_agreement >= ORDER_AGREEMENT:
            return Verdict.SAME
        return Verdict.VARIANT
    if max(contains) >= CONTAINS:
        return Verdict.SUBSET
    return Verdict.UNRELATED


def compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> Comparison:
    """
    Compare two lists by the issues they share and the order they share.

    When either list is marked unordered, the verdict rests on what each
    holds of the other alone.
    """
    lists = [load_model(reading_list) for reading_list in (a, b)]
    sequences = group_rows(
        [reading_list.get(ENTRIES_KEY) or [] for reading_list in lists]
    ).sequences
    a_groups, b_groups = (set(sequence) for sequence in sequences)
    shared = a_groups & b_groups
    union = a_groups | b_groups
    contains = (_share(shared, a_groups), _share(shared, b_groups))
    order_agreement = (
        _order_agreement(sequences, shared) if all(map(is_ordered, lists)) else None
    )
    return Comparison(
        _verdict(contains, order_agreement),
        len(shared) / len(union) if union else 0.0,
        contains,
        order_agreement,
    )
