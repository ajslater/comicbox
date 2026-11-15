"""Compare two lists: the same list, or a different one."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rapidfuzz.distance import LCSseq

from comicbox.readinglists.combine.groups import group_rows
from comicbox.readinglists.schema import ENTRIES_KEY
from comicbox.readinglists.serialize import load_model

# Calibrated on 2026-11-14 against DieselTech CBL lists (fetched to a scratch
# directory, never into the repo), matched by ComicVine id and by name.
# contains is (a in b, b in a); order is order_agreement.
#
#   Civil War       CBRO 132 vs LoCG 116      (0.83, 0.95)  order 0.45
#   House of M      CBRO 64 vs LoCG 51        (0.77, 0.96)  order 0.37
#   Civil War       CBRO 132 vs Official 98   (0.71, 0.96)  order 0.49
#   Civil War       LoCG 116 vs Official 98   (0.84, 0.99)  order 0.98
#   Infinity G.     CBRO 51 vs LoCG 58        (0.92, 0.81)  order 1.00
#   Secret Wars     CBRO 230 vs LoCG 229      (1.00, 1.00)  order 1.00
#   Civil War II    CBRO 153 vs LoCG 152      (0.99, 1.00)  order 1.00
#   Secret Wars     CBRO 230 vs CBH 60        (0.17, 0.67)  order 0.47
#   different events                          (0.00, 0.00)
#   a list against its first half            (0.50, 1.00)  order 1.00
#
# Two curators' takes on one event hold 0.77 to 0.96 of each other, so the
# 0.9 the plan started from called them subsets; 0.75 makes them variants.
# Orders that agree measured 0.98 or more and orders that do not 0.49 or
# less, so 0.9 separates them. DieselTech has no CMRO lists to measure.

# How much of each list the other must hold for the two to be one list.
MATCH_CONTAINS = 0.75
# How much of one list the other must hold for it to be a subset.
SUBSET_CONTAINS = 0.8
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
    issues over their count.
    """

    verdict: Verdict
    overlap: float
    contains: tuple[float, float]
    order_agreement: float


def _share(part: set[int], whole: set[int]) -> float:
    return len(part & whole) / len(whole) if whole else 0.0


def _order_agreement(sequences: Sequence[Sequence[int]], shared: set[int]) -> float:
    if not shared:
        return 0.0
    a, b = ([group for group in sequence if group in shared] for sequence in sequences)
    return LCSseq.similarity(a, b) / len(shared)


def _verdict(contains: tuple[float, float], order_agreement: float) -> Verdict:
    if min(contains) >= MATCH_CONTAINS:
        if order_agreement >= ORDER_AGREEMENT:
            return Verdict.SAME
        return Verdict.VARIANT
    if max(contains) >= SUBSET_CONTAINS:
        return Verdict.SUBSET
    return Verdict.UNRELATED


def compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> Comparison:
    """Compare two lists by the issues they share and the order they share."""
    inputs = [
        load_model(reading_list).get(ENTRIES_KEY) or [] for reading_list in (a, b)
    ]
    sequences = group_rows(inputs).sequences
    a_groups, b_groups = (set(sequence) for sequence in sequences)
    shared = a_groups & b_groups
    union = a_groups | b_groups
    contains = (_share(shared, a_groups), _share(shared, b_groups))
    order_agreement = _order_agreement(sequences, shared)
    return Comparison(
        _verdict(contains, order_agreement),
        len(shared) / len(union) if union else 0.0,
        contains,
        order_agreement,
    )
