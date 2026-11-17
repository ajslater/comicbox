"""
The cover verdict: when a cover search's closest result is taken outright.

The rule is metron-tagger's (Metron-Project/metron-tagger#294): within the
hash's limit, at least 2 bits clear of the next result, and a series that
shares a distinctive word with the comic's.
"""

from __future__ import annotations

import pytest

from comicbox.formats.base.online.cover_hash import (
    FULL_COVER_ACCEPT_BITS,
    HALF_COVER_ACCEPT_BITS,
)
from comicbox.formats.base.online.matcher import (
    COVER_ACCEPT_MARGIN_BITS,
    cover_verdict,
    rank_by_cover_distance,
)
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.formats.base.online.signals import series_words, series_words_agree

_HASH = "95977c2b3129c2d3"
_PROFILE = ComicProfile(series="Lois Lane", issue="5", issue_int=5, year=2020)


def _bits_away(bits: int) -> str:
    """Return a hash exactly ``bits`` bits from `_HASH`."""
    return f"{int(_HASH, 16) ^ ((1 << bits) - 1):016x}"


def _candidate(
    iid: int, cover_hash: str | None = _HASH, series: str = "Lois Lane"
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=iid,
        summary=CandidateSummary(
            series=series,
            issue="5",
            year=2020,
            publisher=None,
            page_count=None,
            cover_url=None,
            variant_label=None,
        ),
        precomputed_cover_hash=cover_hash,
    )


# ------------------------------------------------------------- series words


@pytest.mark.parametrize(
    ("a", "b", "agree"),
    [
        # The three cases metron-tagger#294 names.
        pytest.param("Spider-Man", "Iron Man", False, id="hyphenated-word-is-whole"),
        pytest.param(
            "Batman-Superman", "Batman / Superman", True, id="spaced-slash-joins"
        ),
        pytest.param(
            "Punisher: Red Band",
            "Monster High: Boomuda Triangle",
            False,
            id="cgc-slab-false-match",
        ),
        # A filename that names only part of the series.
        pytest.param(
            "Star Wars", "Star Wars: The Book of Boba Fett", True, id="part-of-name"
        ),
        pytest.param("Star Wars:The Empire", "Empire", True, id="article-on-colon"),
        pytest.param("Pokémon Adventures", "Pokemon", True, id="accents-fold"),
        pytest.param("Alien vs Predator", "The Thing", False, id="stop-words-only"),
        pytest.param("The", "The", False, id="nothing-distinctive"),
        pytest.param("Lois Lane", None, False, id="no-name"),
    ],
)
def test_series_words_agree(a: str | None, b: str | None, *, agree: bool) -> None:
    assert series_words_agree(a, b) is agree


def test_series_words_drops_stop_words_and_volume_and_joins_pairs() -> None:
    assert series_words("Wonder Woman Historia: The Amazons Vol. 2") == {
        "wonder",
        "woman",
        "historia",
        "amazons",
        "wonderwoman",
        "womanhistoria",
        "historiaamazons",
    }


# ------------------------------------------------------------------ ranking


def test_rank_by_cover_distance_sorts_and_drops_uncomparable() -> None:
    far, near, unhashed, tied = (
        _candidate(1, _bits_away(9)),
        _candidate(2, _bits_away(1)),
        _candidate(3, None),
        _candidate(4, _bits_away(9)),
    )

    ranked = rank_by_cover_distance(_HASH, [far, near, unhashed, tied])

    # Stable: the two 9-bit rows keep the order they came in.
    assert [(bits, c.issue_id) for bits, c in ranked] == [(1, 2), (9, 1), (9, 4)]


# ------------------------------------------------------------------ verdict


def _verdict(
    *rows: tuple[int, Candidate],
    accept_bits: int = FULL_COVER_ACCEPT_BITS,
    series_pinned: bool = False,
) -> int | None:
    match = cover_verdict(
        list(rows), accept_bits, _PROFILE, series_pinned=series_pinned
    )
    return match.candidate.issue_id if match else None


def test_a_lone_close_cover_is_accepted() -> None:
    match = cover_verdict(
        [(4, _candidate(1))], FULL_COVER_ACCEPT_BITS, _PROFILE, series_pinned=False
    )

    assert match is not None
    assert (match.candidate.issue_id, match.bits, match.runner_up_bits) == (1, 4, None)
    assert match.n_candidates == 1


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        pytest.param(((FULL_COVER_ACCEPT_BITS, _candidate(1)),), 1, id="at-the-limit"),
        pytest.param(
            ((FULL_COVER_ACCEPT_BITS + 1, _candidate(1)),), None, id="past-the-limit"
        ),
        pytest.param(
            ((2, _candidate(1)), (2 + COVER_ACCEPT_MARGIN_BITS, _candidate(2))),
            1,
            id="leads-by-the-margin",
        ),
        pytest.param(
            ((2, _candidate(1)), (3, _candidate(2))), None, id="leads-by-one-bit"
        ),
        # An issue and a trade paperback sharing a cover.
        pytest.param(((0, _candidate(1)), (0, _candidate(2))), None, id="tie"),
        pytest.param(
            ((3, _candidate(1, series="Monster High")),), None, id="series-disagrees"
        ),
        pytest.param((), None, id="no-results"),
    ],
)
def test_cover_verdict(rows: tuple[tuple[int, Candidate], ...], expected) -> None:
    assert _verdict(*rows) == expected


def test_a_half_spread_is_held_to_the_half_limit() -> None:
    row = (HALF_COVER_ACCEPT_BITS + 1, _candidate(1))

    assert _verdict(row, accept_bits=HALF_COVER_ACCEPT_BITS) is None
    assert _verdict(row, accept_bits=FULL_COVER_ACCEPT_BITS) == 1


def test_a_pinned_series_skips_the_series_check() -> None:
    """With --series-id the search was already limited to the series."""
    row = (3, _candidate(1, series="Superman's Girl Friend"))

    assert _verdict(row) is None
    assert _verdict(row, series_pinned=True) == 1
