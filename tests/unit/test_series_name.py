"""One series normalizer for the online matcher (B6)."""

import random
import re
import string
import time

import pytest

from comicbox.formats.base.online.signals import s_series
from comicbox.series_name import normalize_series
from tests.util.online_matcher import make_candidate, make_profile

# The online matcher's rule before B6, kept to show ASCII names are unchanged.
_OLD_VOLUME_RE = re.compile(
    r"\s*(?:\(\s*)?(?:vol(?:ume|\.)?)\s*\d+\s*\)?", re.IGNORECASE
)
_OLD_NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]+")


def _old_normalize_series(name: str) -> str:
    s = _OLD_VOLUME_RE.sub(" ", name.lower())
    return " ".join(_OLD_NON_ALPHANUM_RE.sub(" ", s).split())


@pytest.mark.parametrize(
    ("comic", "candidate"),
    [
        # The matcher compared "pok mon" with "pokemon".
        ("Pokémon", "Pokemon"),
        # And a non-Latin name as nothing, so it never matched itself.
        ("ワンピース", "ワンピース"),
        ("Человек-паук", "Человек-Паук"),
    ],
)
def test_the_matcher_reads_accents_and_other_scripts(
    comic: str, candidate: str
) -> None:
    profile = make_profile(series=comic)
    assert s_series(profile, make_candidate(series=candidate)) == 1.0


def test_ascii_names_normalize_exactly_as_before() -> None:
    rng = random.Random(0)  # noqa: S311 - a test fixture, not a secret
    alphabet = string.ascii_letters + string.digits + " -_.:()&'!,/" + "  "
    names = [
        "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        for _ in range(5000)
    ]
    names += [
        "X-Men (Vol. 2)",
        "Batman Volume 3",
        "G.I. Joe",
        "  The   Thing  ",
        "vol2",
    ]
    for name in names:
        assert normalize_series(name) == _old_normalize_series(name), name


def test_a_long_run_of_spaces_does_not_stall_the_matcher() -> None:
    """20,000 spaces took 4.9 s through the matcher's volume pattern."""
    profile = make_profile(series="a" + " " * 100_000 + "b")
    start = time.perf_counter()
    s_series(profile, make_candidate(series="a b"))
    assert time.perf_counter() - start < 1
