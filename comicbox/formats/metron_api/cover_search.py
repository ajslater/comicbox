"""
Metron's cover-hash issue search, shaped as the mokkari method it stands in for.

Metron filters its issue list by a cover's perceptual hash (metron#683):
``cover_hash_near`` takes a 64-bit pHash as 16 hex digits, and
``cover_hash_max_distance`` the widest Hamming distance to return, 10 by
default and 20 at most. The rows come back closest first, but the list
serializer omits the distance, so a client recomputes it from each row's
``cover_hash``. mokkari 5.1.0 has no method for this, so callers pass the
filters through ``Session.issues_list(params=...)``, as metron-tagger#294
does.

This module is that method. It imports only the standard library and
mokkari, so it can be lifted into mokkari as it is, or deleted once mokkari
ships its own. Like mokkari's list methods, it annotates and neither filters
nor validates: a bad value is the server's to refuse with a 400, which
mokkari raises as ``ApiError``.

Port map, into mokkari:

- ``issues_by_cover_hash(session, ...)`` becomes a ``CatalogEndpoints``
  method in ``mokkari/_endpoints/catalog.py``, ``session`` becoming
  ``self``.
- ``CoverMatch`` moves to ``mokkari/schemas/issue.py``, and
  ``hamming_distance`` to ``mokkari/utils.py``. The two distance constants
  go with the method.
- ``cache.py``'s issue filter map gains ``cover_hash_near`` and
  ``cover_hash_max_distance`` beside ``"cover_hash": ("image",)``, so an
  update drops a cached cover search only when it changes a cover.
- The tests in ``tests/unit/test_metron_api_cover_search.py`` move to
  ``tests/test_issues.py``, with requests-mock in place of comicbox's fake
  transport.
- ``CHANGELOG.md`` gains an "Unreleased / Added" line.

Removal: there is one caller, ``MetronOnlineSource.search_by_cover`` in
``online_source.py``, through its retry wrapper
``_issues_by_cover_hash_with_retry``. When mokkari ships the method, call
it there and delete this module and its test file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mokkari.schemas.issue import BaseIssue
    from mokkari.session import Session

__all__ = [
    "DEFAULT_COVER_HASH_DISTANCE",
    "MAX_COVER_HASH_DISTANCE",
    "CoverMatch",
    "hamming_distance",
    "issues_by_cover_hash",
]

# The distance Metron uses when a search gives none, and the widest it allows.
DEFAULT_COVER_HASH_DISTANCE: Final = 10
MAX_COVER_HASH_DISTANCE: Final = 20

# A 64-bit pHash as Metron stores and takes it.
_HASH_RE: Final = re.compile(r"[0-9a-fA-F]{16}")


@dataclass(frozen=True, slots=True)
class CoverMatch:
    """
    An issue a cover search returned, and how far its cover is from the hash.

    Attributes:
        issue: The issue, as ``issues_list`` returns it.
        distance: The Hamming distance between the searched hash and the
            issue's ``cover_hash``, or None when the issue's hash is missing
            or not 16 hex digits.

    """

    issue: BaseIssue
    distance: int | None


def hamming_distance(a: str, b: str) -> int | None:
    """
    Count the bits that differ between two hex pHashes.

    Args:
        a: A 64-bit pHash as 16 hex digits.
        b: Another.

    Returns:
        The number of differing bits, 0 to 64, or None when either is not
        16 hex digits.

    """
    if not (_HASH_RE.fullmatch(a) and _HASH_RE.fullmatch(b)):
        return None
    return (int(a, 16) ^ int(b, 16)).bit_count()


def issues_by_cover_hash(
    session: Session,
    cover_hash: str,
    max_distance: int | None = None,
    params: dict[str, str | int] | None = None,
) -> list[CoverMatch]:
    """
    List the issues whose covers are near a perceptual hash.

    One ``issues_list`` call filtered by ``cover_hash_near``. mokkari follows
    the result's pages inside it.

    Args:
        session: The mokkari Session to call.
        cover_hash: The cover's 64-bit pHash as 16 hex digits.
        max_distance: The widest Hamming distance to return, at most
            ``MAX_COVER_HASH_DISTANCE``. None leaves it to the server, which
            uses ``DEFAULT_COVER_HASH_DISTANCE``.
        params: Further ``issues_list`` filters to narrow the search by, such
            as ``number`` or ``series_id``.

    Returns:
        Every row in Metron's order, closest first, each with its distance.

    Raises:
        ApiError: If Metron refuses a filter value, such as a malformed hash
            or a distance out of range, or the request fails.
        RateLimitError: If the Metron API rate limit has been exceeded.

    """
    query: dict[str, str | int] = dict(params or {})
    if max_distance is not None:
        query["cover_hash_max_distance"] = max_distance
    query["cover_hash_near"] = cover_hash
    return [
        CoverMatch(issue, hamming_distance(cover_hash, issue.cover_hash or ""))
        for issue in session.issues_list(params=query)
    ]
